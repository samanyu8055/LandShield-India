"""
build_gsi_training_table.py

Merges positives + pseudo-negatives with terrain, NDVI, and historical
susceptibility features into the final training table. Pure local
merge — no network calls, no fabricated values. Any feature that was
never fetched (fetch script not yet run, or fetch failed for a point)
is left as NaN and counted in the missing-value report below.

INPUTS
------
- data/gsi/gsi_dated_environmental_features.csv   (2,242 positives)
- data/gsi/gsi_pseudo_negative_samples.csv        (4,484 pseudo-negatives)
- data/gsi/gsi_terrain_features.csv               (from fetch_terrain_features_gsi.py)
- data/gsi/gsi_ndvi_features.csv                  (from fetch_ndvi_gsi.py)
- data/gsi/gsi_historical_susceptibility.csv      (from compute_historical_susceptibility_gsi.py)

OUTPUT
------
data/gsi/gsi_ner_training_table.csv
"""

from pathlib import Path

import numpy as np
import pandas as pd

POS_FILE = Path("data/gsi/gsi_dated_environmental_features.csv")
NEG_FILE = Path("data/gsi/gsi_pseudo_negative_samples.csv")
TERRAIN_FILE = Path("data/gsi/gsi_terrain_features.csv")
NDVI_FILE = Path("data/gsi/gsi_ndvi_features.csv")
HIST_FILE = Path("data/gsi/gsi_historical_susceptibility.csv")
OUTPUT_FILE = Path("data/gsi/gsi_ner_training_table.csv")

FINAL_COLUMNS = [
    "record_id", "source", "landslide_event", "State", "latitude", "longitude", "date",
    "rainfall_mm", "rainfall_3day_mm", "soil_moisture",
    "elevation_m", "slope_deg", "ndvi_mean",
    "historical_landslide_density", "historical_landslide_distance",
]


def load_positives() -> pd.DataFrame:
    pos = pd.read_csv(POS_FILE)
    return pd.DataFrame({
        "record_id": pos["Slide_No"],
        "source": "gsi_dated_positive",
        "landslide_event": pos["landslide_event"],
        "State": pos["State"],
        "latitude": pos["Latitude"],
        "longitude": pos["Longitude"],
        "date": pos["event_date"],
        "rainfall_mm": pos["rainfall_mm"],
        "rainfall_3day_mm": pos["rainfall_3day_mm"],
        "soil_moisture": pos["soil_moisture"],
    })


def load_negatives() -> pd.DataFrame:
    neg = pd.read_csv(NEG_FILE)
    return pd.DataFrame({
        "record_id": neg["record_id"],
        "source": neg["source"],
        "landslide_event": neg["landslide_event"],
        "State": neg["State"],
        "latitude": neg["Latitude"],
        "longitude": neg["Longitude"],
        "date": neg["date"],
        # Rainfall/soil moisture were never fetched for pseudo-negatives in
        # the pseudo-negative stage -> left as genuine NaN, not fabricated.
        "rainfall_mm": np.nan,
        "rainfall_3day_mm": np.nan,
        "soil_moisture": np.nan,
    })


def merge_terrain(df: pd.DataFrame) -> pd.DataFrame:
    if not TERRAIN_FILE.exists():
        print(f"WARNING: {TERRAIN_FILE} not found — elevation_m/slope_deg will be all-NaN. "
              f"Run fetch_terrain_features_gsi.py first.")
        df["elevation_m"] = np.nan
        df["slope_deg"] = np.nan
        return df

    terrain = pd.read_csv(TERRAIN_FILE)
    terrain = terrain[terrain["terrain_status"] == "ok"].copy()
    terrain["lat_key"] = terrain["latitude"].round(5)
    terrain["lon_key"] = terrain["longitude"].round(5)
    df["lat_key"] = df["latitude"].round(5)
    df["lon_key"] = df["longitude"].round(5)

    df = df.merge(
        terrain[["lat_key", "lon_key", "elevation_m", "slope_deg"]],
        on=["lat_key", "lon_key"], how="left",
    ).drop(columns=["lat_key", "lon_key"])
    return df


def merge_ndvi(df: pd.DataFrame) -> pd.DataFrame:
    if not NDVI_FILE.exists():
        print(f"WARNING: {NDVI_FILE} not found — ndvi_mean will be all-NaN. "
              f"Run fetch_ndvi_gsi.py first.")
        df["ndvi_mean"] = np.nan
        return df

    ndvi = pd.read_csv(NDVI_FILE)
    ndvi = ndvi[ndvi["ndvi_status"] == "ok"][["record_id", "ndvi_mean"]]
    df = df.merge(ndvi, on="record_id", how="left")
    return df


def merge_historical(df: pd.DataFrame) -> pd.DataFrame:
    if not HIST_FILE.exists():
        print(f"WARNING: {HIST_FILE} not found — historical features will be all-NaN. "
              f"Run compute_historical_susceptibility_gsi.py first.")
        df["historical_landslide_density"] = np.nan
        df["historical_landslide_distance"] = np.nan
        return df

    hist = pd.read_csv(HIST_FILE)[
        ["record_id", "historical_landslide_density", "historical_landslide_distance"]
    ]
    df = df.merge(hist, on="record_id", how="left")
    return df


def main():
    pos = load_positives()
    neg = load_negatives()
    df = pd.concat([pos, neg], ignore_index=True)

    df = merge_terrain(df)
    df = merge_ndvi(df)
    df = merge_historical(df)

    df = df[FINAL_COLUMNS]

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUTPUT_FILE, index=False)

    # ---- report ----
    n_pos = int((df["landslide_event"] == 1).sum())
    n_neg = int((df["landslide_event"] == 0).sum())
    dup_ids = int(df["record_id"].duplicated().sum())
    dup_latlon_date = int(df.duplicated(subset=["latitude", "longitude", "date"]).sum())

    print("\n" + "=" * 70)
    print("FINAL TRAINING TABLE REPORT")
    print("=" * 70)
    print(f"Total rows: {len(df)}")
    print(f"Positives (landslide_event=1): {n_pos}")
    print(f"Negatives (landslide_event=0): {n_neg}")
    print(f"Duplicate record_id: {dup_ids}")
    print(f"Duplicate (lat, lon, date) rows: {dup_latlon_date}")
    print("\nMissing values by column:")
    print(df.isna().sum().to_string())
    print(f"\nSaved: {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
