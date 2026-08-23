"""
train_landslide_model.py

SIH26001 LandslideShield -- Model V1
"Landslide Susceptibility / Risk Classification Model"

Trains the FIRST working landslide susceptibility classifier using ONLY
4 terrain/history features. rainfall_mm, rainfall_3day_mm, soil_moisture,
and ndvi_mean are deliberately excluded from V1 (see known_limitations
in the saved metrics file for why).

INPUT
-----
data/gsi/gsi_ner_training_table.csv

OUTPUTS
-------
models/landslide_xgb.pkl
data/gsi/gsi_model_training.csv   (cleaned table actually used for train/test)
data/gsi/model_metrics.json
data/gsi/test_predictions.csv

KNOWN LIMITATION -- POSSIBLE TEMPORAL LEAKAGE IN HISTORICAL FEATURES
----------------------------------------------------------------------
historical_landslide_density and historical_landslide_distance were
computed in compute_historical_susceptibility_gsi.py against the
COMPLETE GSI inventory (35,716 records) with NO date cutoff relative to
each sample's own event date. So for any sample that is not the most
recent landslide in its area, these two features may reflect landslides
that occurred AFTER that sample's date -- i.e. the model can "see into
the future" through these two features.

This script does NOT fix that, because fixing it requires recomputing
density/distance with a per-sample date cutoff against the raw
inventory file (data/gsi/gsi_landslide_inventory_normalized.csv), which
was not part of this handoff and this script does not have access to.
Treat this V1 model's reported metrics as an OPTIMISTIC UPPER BOUND
until that recomputation is done. This is reported here, not hidden --
see the printed warning below and the "known_limitations" field in
model_metrics.json.
"""

from pathlib import Path
import json
import pickle
import sys

import numpy as np
import pandas as pd
from sklearn.metrics import (
    accuracy_score,
    precision_score,
    recall_score,
    f1_score,
    roc_auc_score,
    confusion_matrix,
)

try:
    import xgboost as xgb
except ImportError:
    print("ERROR: xgboost is not installed in this environment.")
    print("Install it with the following command, then re-run this script:")
    print()
    print("    pip install xgboost")
    print()
    sys.exit(1)

# ---------------------------------------------------------------
# Config
# ---------------------------------------------------------------
INPUT_FILE = Path("data/gsi/gsi_ner_training_table.csv")
CLEANED_OUTPUT = Path("data/gsi/gsi_model_training.csv")
MODEL_OUTPUT = Path("models/landslide_xgb.pkl")
METRICS_OUTPUT = Path("data/gsi/model_metrics.json")
PREDICTIONS_OUTPUT = Path("data/gsi/test_predictions.csv")

FEATURES = [
    "elevation_m",
    "slope_deg",
    "historical_landslide_density",
    "historical_landslide_distance",
]
TARGET = "landslide_event"

GRID_SIZE_DEG = 0.5        # spatial split grid cell size (degrees lat/lon)
TEST_CELL_FRACTION = 0.2   # ~20% of grid cells held out for test
RANDOM_SEED = 42

MODEL_NAME = "Landslide Susceptibility / Risk Classification Model"


def log(msg):
    print(msg, flush=True)


# ---------------------------------------------------------------
# Step 1: load + clean
# ---------------------------------------------------------------
def load_and_clean() -> pd.DataFrame:
    if not INPUT_FILE.exists():
        log(f"FATAL: {INPUT_FILE} not found. Run build_gsi_training_table.py first.")
        sys.exit(1)

    df = pd.read_csv(INPUT_FILE)
    n0 = len(df)
    log(f"Loaded {n0} rows from {INPUT_FILE}")

    # 1. drop rows with missing record_id -- can't safely dedupe or trace
    #    predictions back to a sample without one
    df = df.dropna(subset=["record_id"])
    n1 = len(df)
    log(f"Dropped {n0 - n1} row(s) with missing record_id -> {n1} rows")

    # 2. drop duplicate record_id (keep first occurrence)
    dup_id = int(df["record_id"].duplicated().sum())
    df = df.drop_duplicates(subset=["record_id"], keep="first")
    n2 = len(df)
    log(f"Dropped {dup_id} duplicate record_id row(s) -> {n2} rows")

    # 3. drop duplicate (latitude, longitude, date)
    dup_lld = int(df.duplicated(subset=["latitude", "longitude", "date"]).sum())
    df = df.drop_duplicates(subset=["latitude", "longitude", "date"], keep="first")
    n3 = len(df)
    log(f"Dropped {dup_lld} duplicate (latitude, longitude, date) row(s) -> {n3} rows")

    # 4. drop rows with missing/invalid (NaN, inf) values in the 4 model features
    #    -- never fabricate/impute these
    before_feat = len(df)
    df = df.dropna(subset=FEATURES)
    df = df[np.isfinite(df[FEATURES]).all(axis=1)]
    n4 = len(df)
    log(f"Dropped {before_feat - n4} row(s) with missing/invalid {FEATURES} -> {n4} rows")

    df = df.reset_index(drop=True)

    n_pos = int((df[TARGET] == 1).sum())
    n_neg = int((df[TARGET] == 0).sum())
    log(f"\nFinal cleaned training table: {len(df)} rows "
        f"({n_pos} positives, {n_neg} negatives)")

    CLEANED_OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(CLEANED_OUTPUT, index=False)
    log(f"Saved cleaned table -> {CLEANED_OUTPUT}\n")

    return df


# ---------------------------------------------------------------
# Step 2: spatial train/test split (0.5-degree grid cells)
# ---------------------------------------------------------------
def spatial_split(df: pd.DataFrame):
    df = df.copy()
    df["grid_lat"] = np.floor(df["latitude"] / GRID_SIZE_DEG) * GRID_SIZE_DEG
    df["grid_lon"] = np.floor(df["longitude"] / GRID_SIZE_DEG) * GRID_SIZE_DEG
    df["grid_cell"] = df["grid_lat"].astype(str) + "_" + df["grid_lon"].astype(str)

    # sorted() before permutation is what makes this reproducible across
    # runs/machines -- unique() order otherwise depends on row order in
    # the input file, which is not guaranteed stable.
    cells = sorted(df["grid_cell"].unique())
    rng = np.random.RandomState(RANDOM_SEED)
    shuffled_cells = rng.permutation(cells)
    n_test_cells = max(1, int(len(cells) * TEST_CELL_FRACTION))
    test_cells = set(shuffled_cells[:n_test_cells])

    df["split"] = np.where(df["grid_cell"].isin(test_cells), "test", "train")

    drop_cols = ["grid_lat", "grid_lon", "grid_cell", "split"]
    train_df = df[df["split"] == "train"].drop(columns=drop_cols).reset_index(drop=True)
    test_df = df[df["split"] == "test"].drop(columns=drop_cols).reset_index(drop=True)

    log(f"Spatial split: {GRID_SIZE_DEG} deg grid -> {len(cells)} unique cells, "
        f"{n_test_cells} held out for test (seed={RANDOM_SEED})")
    log(f"Train: {len(train_df)} rows | Test: {len(test_df)} rows")
    log(f"Train class counts: {train_df[TARGET].value_counts().to_dict()}")
    log(f"Test class counts:  {test_df[TARGET].value_counts().to_dict()}\n")

    return train_df, test_df


# ---------------------------------------------------------------
# Step 3: train
# ---------------------------------------------------------------
def train_model(train_df: pd.DataFrame):
    X_train = train_df[FEATURES]
    y_train = train_df[TARGET]

    n_pos = int((y_train == 1).sum())
    n_neg = int((y_train == 0).sum())
    scale_pos_weight = (n_neg / n_pos) if n_pos > 0 else 1.0
    log(f"Class imbalance handling: scale_pos_weight = {n_neg}/{n_pos} = {scale_pos_weight:.3f}")

    model = xgb.XGBClassifier(
        n_estimators=300,
        max_depth=4,
        learning_rate=0.05,
        subsample=0.8,
        colsample_bytree=0.8,
        objective="binary:logistic",
        eval_metric="logloss",
        scale_pos_weight=scale_pos_weight,
        random_state=RANDOM_SEED,
        n_jobs=-1,
    )
    model.fit(X_train, y_train)
    log("Model trained.\n")
    return model


# ---------------------------------------------------------------
# Step 4: evaluate + save
# ---------------------------------------------------------------
def evaluate(model, train_df, test_df):
    X_test = test_df[FEATURES]
    y_test = test_df[TARGET]

    proba = model.predict_proba(X_test)[:, 1]
    pred = (proba >= 0.5).astype(int)

    acc = float(accuracy_score(y_test, pred))
    prec = float(precision_score(y_test, pred, zero_division=0))
    rec = float(recall_score(y_test, pred, zero_division=0))
    f1 = float(f1_score(y_test, pred, zero_division=0))
    auc = float(roc_auc_score(y_test, proba))
    cm = confusion_matrix(y_test, pred)

    log("=" * 70)
    log(f"EVALUATION -- {MODEL_NAME}")
    log("=" * 70)
    log(f"Accuracy:  {acc:.4f}")
    log(f"Precision: {prec:.4f}")
    log(f"Recall:    {rec:.4f}")
    log(f"F1:        {f1:.4f}")
    log(f"ROC-AUC:   {auc:.4f}")
    log(f"Confusion matrix [[TN FP] [FN TP]]:\n{cm}")

    importances = dict(zip(FEATURES, [float(v) for v in model.feature_importances_]))
    importances = dict(sorted(importances.items(), key=lambda x: -x[1]))
    log("\nFeature importance:")
    for feat, imp in importances.items():
        log(f"  {feat}: {imp:.4f}")

    metrics = {
        "model_name": MODEL_NAME,
        "features_used": FEATURES,
        "target": TARGET,
        "random_seed": RANDOM_SEED,
        "grid_size_deg": GRID_SIZE_DEG,
        "train_rows": len(train_df),
        "test_rows": len(test_df),
        "train_class_counts": {str(k): int(v) for k, v in train_df[TARGET].value_counts().to_dict().items()},
        "test_class_counts": {str(k): int(v) for k, v in test_df[TARGET].value_counts().to_dict().items()},
        "accuracy": acc,
        "precision": prec,
        "recall": rec,
        "f1_score": f1,
        "roc_auc": auc,
        "confusion_matrix": {
            "true_negative": int(cm[0][0]),
            "false_positive": int(cm[0][1]),
            "false_negative": int(cm[1][0]),
            "true_positive": int(cm[1][1]),
        },
        "feature_importance": importances,
        "disclaimer": (
            f"{MODEL_NAME}: predicted_score is a relative risk/susceptibility "
            "score learned from historical patterns, NOT a scientifically "
            "validated landslide probability, and this model does NOT "
            "predict the occurrence, timing, or exact location of a "
            "specific future landslide event."
        ),
        "known_limitations": [
            "Possible temporal leakage: historical_landslide_density and "
            "historical_landslide_distance were computed in "
            "compute_historical_susceptibility_gsi.py against the full GSI "
            "inventory (35,716 records) with no date cutoff. For samples "
            "that are not the most recent landslide in their area, these "
            "two features may include landslides that occurred AFTER the "
            "sample's own date. This was not fixed here because the raw "
            "inventory file (gsi_landslide_inventory_normalized.csv) "
            "needed to recompute time-safe density/distance per sample "
            "date was not provided in this handoff. Treat these metrics "
            "as an optimistic upper bound until the historical features "
            "are recomputed with a per-sample date cutoff.",
            "V1 uses only 4 static/terrain features (elevation, slope, "
            "historical density, historical distance). rainfall_mm, "
            "rainfall_3day_mm, soil_moisture, and ndvi_mean are excluded "
            "from V1 due to high missingness in the current table and are "
            "reserved for a later model version.",
        ],
    }

    METRICS_OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with open(METRICS_OUTPUT, "w") as f:
        json.dump(metrics, f, indent=2)
    log(f"\nSaved metrics -> {METRICS_OUTPUT}")

    preds_df = test_df[["record_id", "latitude", "longitude", "date"]].copy()
    preds_df["actual_label"] = y_test.values
    preds_df["predicted_label"] = pred
    preds_df["predicted_score"] = proba
    PREDICTIONS_OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    preds_df.to_csv(PREDICTIONS_OUTPUT, index=False)
    log(f"Saved test predictions -> {PREDICTIONS_OUTPUT}")

    return metrics


# ---------------------------------------------------------------
# main
# ---------------------------------------------------------------
def main():
    log("=" * 70)
    log(f"TRAINING: {MODEL_NAME} (V1)")
    log("=" * 70)
    log("\nWARNING: possible temporal leakage in historical_landslide_density "
        "/ historical_landslide_distance -- see 'known_limitations' in the "
        "saved model_metrics.json for full detail.\n")

    df = load_and_clean()
    train_df, test_df = spatial_split(df)

    if len(train_df) == 0 or len(test_df) == 0:
        log("FATAL: spatial split produced an empty train or test set. "
            "Adjust GRID_SIZE_DEG or TEST_CELL_FRACTION.")
        sys.exit(1)

    model = train_model(train_df)
    evaluate(model, train_df, test_df)

    MODEL_OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with open(MODEL_OUTPUT, "wb") as f:
        pickle.dump(model, f)
    log(f"\nSaved model -> {MODEL_OUTPUT}")
    log("\nDone. First working model trained successfully.")


if __name__ == "__main__":
    main()
