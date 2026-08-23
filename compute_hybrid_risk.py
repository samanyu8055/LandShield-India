"""
compute_hybrid_risk.py

Heuristic hybrid landslide RISK ENGINE for the Sikkim pilot.

THIS IS NOT A TRAINED / SUPERVISED MODEL.
It does not fit weights or thresholds from labeled data, does not report
accuracy, precision, recall, or any classifier performance metric, and
makes no claim of statistical predictive validity. The dataset currently
has exactly 1 documented landslide-day label (Mangan, 2024-06-13) out of
610 rows, which is not enough to train or evaluate a supervised classifier
(see train_model.py, which is left untouched and reserved for Phase 2,
once a larger dated inventory is available).

Instead, this script combines real, already-computed features into a
transparent, DOCUMENTED weighted-overlay score:

  SUSCEPTIBILITY (60% of risk_score) - static, per-location hazard
  predisposition, built from terrain + historical Bhuvan landslide
  inventory features:
      slope_deg                              20%
      nearest_landslide_distance_km          15%  (inverse - closer = higher risk)
      landslide_density_nearby               10%
      historical_landslide_area_nearby        5%
      ndvi_mean                               5%  (inverse - less vegetation = higher risk)
      elevation_m                             5%

  TRIGGER (40% of risk_score) - dynamic, day-to-day conditions:
      3-day rolling rainfall accumulation    25%
      soil_moisture                          15%

  risk_score = 0.60 * susceptibility_score + 0.40 * trigger_score   (0-100 scale)

The single documented Mangan event is used only as a QUALITATIVE SANITY
CHECK at the end of this script (does the engine flag that known real
event as elevated?) - it is never used to fit, tune, or validate any
weight or threshold in this script.

Output is written to sikkim_risk_scores.csv (schema-compatible with the
existing make_map.py / make_impact_priority.py, which only require
location, lat, lon, date, risk_score, top_risk_factor).
"""

import shutil

import pandas as pd

MASTER_CSV = "sikkim_master_features.csv"
OUTPUT_CSV = "sikkim_risk_scores.csv"
BACKUP_CSV = "sikkim_risk_scores_backup.csv"

ROLLING_WINDOW_DAYS = 3

# --------------------------------------------------------------------------
# Weights (absolute, out of 100%). Sums: susceptibility = 60, trigger = 40.
# --------------------------------------------------------------------------
WEIGHTS = {
    "slope_deg": 0.20,
    "nearest_landslide_distance_km": 0.15,   # inverse
    "landslide_density_nearby": 0.10,
    "historical_landslide_area_nearby": 0.05,
    "ndvi_mean": 0.05,                       # inverse
    "elevation_m": 0.05,
    "rainfall_3day_mm": 0.25,
    "soil_moisture": 0.15,
}
SUSCEPTIBILITY_FEATURES = [
    "slope_deg",
    "nearest_landslide_distance_km",
    "landslide_density_nearby",
    "historical_landslide_area_nearby",
    "ndvi_mean",
    "elevation_m",
]
TRIGGER_FEATURES = ["rainfall_3day_mm", "soil_moisture"]
INVERSE_FEATURES = {"nearest_landslide_distance_km", "ndvi_mean"}

SUSCEPTIBILITY_WEIGHT_TOTAL = sum(WEIGHTS[f] for f in SUSCEPTIBILITY_FEATURES)  # 0.60
TRIGGER_WEIGHT_TOTAL = sum(WEIGHTS[f] for f in TRIGGER_FEATURES)                # 0.40

assert abs(SUSCEPTIBILITY_WEIGHT_TOTAL - 0.60) < 1e-9
assert abs(TRIGGER_WEIGHT_TOTAL - 0.40) < 1e-9


def robust_minmax_normalize(series, invert=False):
    """
    Min-max normalize a pandas Series to [0, 1].
    "Robust" here means: guard against a degenerate zero-range input
    (all values identical) by returning 0.5 for every row instead of
    dividing by zero - this is a documented fallback, not a real
    scenario in the current 5-location dataset (verified beforehand:
    none of the 6 static features are degenerate across the 5 Sikkim
    pilot locations).
    """
    lo, hi = series.min(), series.max()
    if hi - lo == 0:
        norm = pd.Series(0.5, index=series.index)
    else:
        norm = (series - lo) / (hi - lo)
    if invert:
        norm = 1 - norm
    return norm


def classify_risk_level(score):
    if score <= 30:
        return "Low"
    elif score <= 60:
        return "Moderate"
    elif score <= 80:
        return "High"
    else:
        return "Very High"


def main():
    # ---- backup existing risk scores before replacing ----
    shutil.copyfile(OUTPUT_CSV, BACKUP_CSV)
    print(f"Backed up {OUTPUT_CSV} -> {BACKUP_CSV}")

    df = pd.read_csv(MASTER_CSV, parse_dates=["date"])
    df = df.sort_values(["location", "date"]).reset_index(drop=True)
    print(f"\nLoaded {MASTER_CSV}: {len(df)} rows, {df['location'].nunique()} locations")

    # ----------------------------------------------------------------
    # TRIGGER: 3-day rolling rainfall accumulation (per location, since
    # each location's 122 days are an independent daily time series).
    # min_periods=1 means the first 1-2 days of each location's series
    # use whatever days are actually available (1 or 2 days) rather than
    # producing NaN - documented here as an edge-case, not fabricated data:
    # no rainfall values are invented, the window is just smaller at the
    # very start of each location's record.
    # ----------------------------------------------------------------
    df["rainfall_3day_mm"] = (
        df.groupby("location")["rainfall_mm"]
        .transform(lambda s: s.rolling(window=ROLLING_WINDOW_DAYS, min_periods=1).sum())
    )

    # ----------------------------------------------------------------
    # SUSCEPTIBILITY: static per-location features, normalized with
    # min-max ACROSS THE FIVE LOCATIONS (each static feature has exactly
    # one value per location, repeated across its 122 daily rows).
    # ----------------------------------------------------------------
    per_location_static = df.groupby("location")[SUSCEPTIBILITY_FEATURES].first()
    static_norm = pd.DataFrame(index=per_location_static.index)
    for feat in SUSCEPTIBILITY_FEATURES:
        static_norm[f"{feat}_norm"] = robust_minmax_normalize(
            per_location_static[feat], invert=(feat in INVERSE_FEATURES)
        )

    susceptibility_score_per_loc = pd.Series(0.0, index=per_location_static.index)
    for feat in SUSCEPTIBILITY_FEATURES:
        susceptibility_score_per_loc += WEIGHTS[feat] * static_norm[f"{feat}_norm"]
    susceptibility_score_per_loc = 100 * susceptibility_score_per_loc / SUSCEPTIBILITY_WEIGHT_TOTAL

    static_norm["susceptibility_score"] = susceptibility_score_per_loc
    df = df.merge(static_norm.reset_index(), on="location", how="left")

    # ----------------------------------------------------------------
    # TRIGGER: dynamic features, normalized with min-max ACROSS THE FULL
    # DATASET (all 610 daily rows) - reflects how anomalous a given day's
    # rainfall/soil-moisture is relative to the whole June-Sept 2024
    # observation window, across all locations.
    # ----------------------------------------------------------------
    for feat in TRIGGER_FEATURES:
        df[f"{feat}_norm"] = robust_minmax_normalize(df[feat], invert=(feat in INVERSE_FEATURES))

    trigger_score = pd.Series(0.0, index=df.index)
    for feat in TRIGGER_FEATURES:
        trigger_score += WEIGHTS[feat] * df[f"{feat}_norm"]
    df["trigger_score"] = 100 * trigger_score / TRIGGER_WEIGHT_TOTAL

    # ----------------------------------------------------------------
    # COMBINED RISK SCORE
    # ----------------------------------------------------------------
    df["risk_score"] = (0.60 * df["susceptibility_score"] + 0.40 * df["trigger_score"]).round(2)
    df["susceptibility_score"] = df["susceptibility_score"].round(2)
    df["trigger_score"] = df["trigger_score"].round(2)
    df["risk_level"] = df["risk_score"].apply(classify_risk_level)

    # ----------------------------------------------------------------
    # top_risk_factor: the feature whose WEIGHTED CONTRIBUTION
    # (weight * normalized value) to this row's score is largest.
    # ----------------------------------------------------------------
    all_features = SUSCEPTIBILITY_FEATURES + TRIGGER_FEATURES
    contributions = pd.DataFrame(
        {feat: WEIGHTS[feat] * df[f"{feat}_norm"] for feat in all_features}
    )
    df["top_risk_factor"] = contributions.idxmax(axis=1)

    # ----------------------------------------------------------------
    # Output - keep schema compatible with make_map.py / make_impact_priority.py
    # (they only require location, lat, lon, date, risk_score, top_risk_factor).
    # Keep the original feature columns too, plus the new engine outputs.
    # ----------------------------------------------------------------
    output_cols = [
        "location", "lat", "lon", "date",
        "rainfall_mm", "rainfall_3day_mm", "soil_moisture",
        "elevation_m", "slope_deg", "ndvi_mean",
        "nearest_landslide_distance_km", "spatial_landslide_presence",
        "landslide_density_nearby", "historical_landslide_area_nearby",
        "is_landslide_day",
        "susceptibility_score", "trigger_score", "risk_score", "risk_level",
        "top_risk_factor",
    ]
    out_df = df[output_cols].copy()
    out_df["date"] = out_df["date"].dt.strftime("%Y-%m-%d")
    out_df.to_csv(OUTPUT_CSV, index=False)

    print(f"\nSaved {OUTPUT_CSV}")
    print(f"Total rows: {len(out_df)}")
    print(f"Columns ({len(out_df.columns)}): {out_df.columns.tolist()}")

    print("\nFirst 10 generated rows:")
    print(out_df.head(10).to_string(index=False))

    print("\nRisk score summary:")
    print(f"  min:  {out_df['risk_score'].min():.2f}")
    print(f"  max:  {out_df['risk_score'].max():.2f}")
    print(f"  mean: {out_df['risk_score'].mean():.2f}")

    print("\nRisk level counts:")
    print(out_df["risk_level"].value_counts().reindex(["Low", "Moderate", "High", "Very High"]).fillna(0).astype(int))

    print("\nQualitative sanity check - Mangan, 2024-06-13 (the one documented event):")
    sanity_row = out_df[(out_df["location"] == "Mangan") & (out_df["date"] == "2024-06-13")]
    print(sanity_row.to_string(index=False))
    print(
        "\nThis is a qualitative check only (does the engine flag the one known real event\n"
        "as elevated?) - it was NOT used to fit or tune any weight, threshold, or\n"
        "normalization in this script, and this script makes NO claim of predictive\n"
        "accuracy, precision, recall, or statistical validation. It is a documented\n"
        "heuristic weighted-overlay risk engine, not a trained/evaluated model."
    )


if __name__ == "__main__":
    main()
