"""
compute_historical_susceptibility_gsi.py

Adds historical_landslide_density and historical_landslide_distance to
every positive and pseudo-negative sample, using the COMPLETE GSI
landslide inventory (gsi_landslide_inventory_normalized.csv, 35,716
records) as the historical reference catalog. Pure local computation —
no network calls.

DEFINITIONS
-----------
- historical_landslide_distance: great-circle distance (km) from the
  sample to the NEAREST inventory landslide.
- historical_landslide_density: count of inventory landslides within
  DENSITY_RADIUS_KM (default 10 km) of the sample.

SELF-EXCLUSION (no leakage)
----------------------------
Every positive sample IS one of the inventory records (by Slide_No).
If we included it, distance-to-nearest would trivially be 0 km and
density would always count itself. So for each positive sample, its own
Slide_No is excluded from the reference catalog before computing its
distance/density. Pseudo-negatives are not inventory members, so no
exclusion is needed for them (they were already generated with a 1km
exclusion buffer from the inventory in the pseudo-negative stage).

METHOD
------
Haversine distance via a BallTree (sklearn, metric="haversine") for
efficient nearest-neighbor and radius queries across ~6.7k samples vs
~35.7k inventory points.
"""

from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.neighbors import BallTree

POS_FILE = Path("data/gsi/gsi_dated_environmental_features.csv")
NEG_FILE = Path("data/gsi/gsi_pseudo_negative_samples.csv")
INVENTORY_FILE = Path("data/gsi/gsi_landslide_inventory_normalized.csv")
OUTPUT_FILE = Path("data/gsi/gsi_historical_susceptibility.csv")

DENSITY_RADIUS_KM = 10.0
EARTH_RADIUS_KM = 6371.0088


def load_inventory() -> pd.DataFrame:
    inv = pd.read_csv(INVENTORY_FILE)
    inv = inv.dropna(subset=["Latitude", "Longitude"]).reset_index(drop=True)
    return inv[["Slide_No", "Latitude", "Longitude"]]


def load_samples() -> pd.DataFrame:
    pos = pd.read_csv(POS_FILE)[["Slide_No", "Latitude", "Longitude"]].rename(
        columns={"Slide_No": "record_id"}
    )
    pos["is_inventory_member"] = True

    neg = pd.read_csv(NEG_FILE)[["record_id", "Latitude", "Longitude"]]
    neg["is_inventory_member"] = False

    combined = pd.concat([pos, neg], ignore_index=True)
    combined = combined.dropna(subset=["Latitude", "Longitude"]).reset_index(drop=True)
    return combined


def main():
    inv = load_inventory()
    samples = load_samples()

    print(f"Historical inventory (reference catalog): {len(inv)} records")
    print(f"Samples to score (positive + pseudo-negative): {len(samples)}")
    print(f"Density radius: {DENSITY_RADIUS_KM} km\n")

    inv_coords_rad = np.radians(inv[["Latitude", "Longitude"]].to_numpy())
    tree = BallTree(inv_coords_rad, metric="haversine")
    radius_rad = DENSITY_RADIUS_KM / EARTH_RADIUS_KM

    inv_slide_no = inv["Slide_No"].to_numpy()
    n_self_excluded = 0
    results = []

    for row in samples.itertuples():
        query = np.radians([[row.Latitude, row.Longitude]])

        # Query more neighbors than we need so we can drop a self-match.
        k = 2 if row.is_inventory_member else 1
        dist_rad, idx = tree.query(query, k=k)
        dist_km = dist_rad[0] * EARTH_RADIUS_KM
        idx = idx[0]

        if row.is_inventory_member:
            # Drop the self-match (same Slide_No) if present among neighbors.
            keep = [i for i in range(len(idx)) if inv_slide_no[idx[i]] != row.record_id]
            if len(keep) < len(idx):
                n_self_excluded += 1
            if keep:
                nearest_dist = dist_km[keep[0]]
            else:
                # fell back: re-query wider excluding self via radius scan
                nearest_dist = np.nan
        else:
            nearest_dist = dist_km[0]

        # Density: radius count, then subtract 1 if the point itself is a
        # member of the inventory (it will always be within its own radius).
        count_idx = tree.query_radius(query, r=radius_rad)[0]
        density = len(count_idx)
        if row.is_inventory_member:
            self_in_radius = any(inv_slide_no[i] == row.record_id for i in count_idx)
            if self_in_radius:
                density -= 1

        results.append(
            {
                "record_id": row.record_id,
                "latitude": row.Latitude,
                "longitude": row.Longitude,
                "historical_landslide_distance": round(float(nearest_dist), 3) if not np.isnan(nearest_dist) else np.nan,
                "historical_landslide_density": int(density),
            }
        )

    out = pd.DataFrame(results)
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(OUTPUT_FILE, index=False)

    print(f"Self-matches excluded (positives that are inventory members): {n_self_excluded}")
    print(f"Rows with unresolved distance (self-exclusion left no neighbor): {out['historical_landslide_distance'].isna().sum()}")
    print(f"\nSaved {OUTPUT_FILE} ({len(out)} rows)")
    print(out.describe(include="all"))


if __name__ == "__main__":
    main()
