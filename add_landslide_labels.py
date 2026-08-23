import json
import math
import shutil

import pandas as pd

# --------------------------------------------------------------------------
# INPUTS
# --------------------------------------------------------------------------
GEOJSON_PATH = "data/landslides/sikkim_2023_landslides.geojson"
MASTER_CSV = "sikkim_master_features.csv"
BACKUP_CSV = "sikkim_master_features_backup.csv"

RADIUS_KM = 10.0

# --------------------------------------------------------------------------
# DOCUMENTED EVENT LABEL (unchanged from the original script)
# --------------------------------------------------------------------------
# Manually compiled from verified news reports (COOLR/Bhuvan access unavailable
# for a dated 2024 inventory). Only events falling within our June-Sept 2024
# data window are usable as positive labels for is_landslide_day.
documented_events = [
    {
        "location": "Mangan",
        "date": "2024-06-13",
        "event": "Landslide following heavy rainfall in North Sikkim, 3 deaths, houses destroyed",
        "source": "Multiple news reports (AIR/newsonair.gov.in, June 13 2024)",
    },
]

# --------------------------------------------------------------------------
# PURE-PYTHON GEOMETRY FALLBACK (geopandas / shapely not available in this
# environment, and no network access to install them). Approximations used
# are documented at each function.
# --------------------------------------------------------------------------


def haversine_km(lat1, lon1, lat2, lon2):
    """Great-circle distance in km between two (lat, lon) points."""
    R = 6371.0088
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


def point_in_ring(lon, lat, ring):
    """
    Standard ray-casting point-in-polygon test on a single linear ring.
    APPROXIMATION: operates directly on (lon, lat) as planar coordinates
    (no map projection). For polygons this small (tens to low hundreds of
    meters across, per the Length/Width fields in the source data) the
    curvature of the earth over that extent is negligible, so this is a
    standard and accepted approximation for point-in-polygon at this scale.
    """
    inside = False
    n = len(ring)
    x, y = lon, lat
    j = n - 1
    for i in range(n):
        xi, yi = ring[i][0], ring[i][1]
        xj, yj = ring[j][0], ring[j][1]
        intersects = ((yi > y) != (yj > y)) and (
            x < (xj - xi) * (y - yi) / (yj - yi + 1e-15) + xi
        )
        if intersects:
            inside = not inside
        j = i
    return inside


def point_in_multipolygon(lon, lat, multipolygon_coords):
    """
    multipolygon_coords: GeoJSON MultiPolygon coordinates array
    (list of polygons -> list of rings -> list of [lon, lat] points).
    A point is "in" the multipolygon if it is inside the exterior ring
    of any part and not inside any of that part's interior rings (holes).
    (Inspected data: none of the 335 features in this file have holes or
    multiple polygon parts, but the general case is handled anyway.)
    """
    for polygon in multipolygon_coords:
        if not polygon:
            continue
        exterior = polygon[0]
        if not point_in_ring(lon, lat, exterior):
            continue
        in_hole = False
        for hole in polygon[1:]:
            if point_in_ring(lon, lat, hole):
                in_hole = True
                break
        if not in_hole:
            return True
    return False


def load_landslide_features(path):
    with open(path) as f:
        gj = json.load(f)
    feats = []
    for feat in gj["features"]:
        props = feat["properties"]
        feats.append(
            {
                "slide_no": props.get("Slide_No"),
                # Representative point per feature. Verified against the
                # polygon geometry: matches the vertex-average centroid of
                # the polygon (checked on feature 0: centroid (88.33941,
                # 27.11126) vs properties Latitude/Longitude (27.1113,
                # 88.3395) - effectively identical). Used as the feature's
                # location for distance/density/area calculations.
                "lat": props.get("Latitude"),
                "lon": props.get("Longitude"),
                "area": props.get("Area"),  # as provided by source (see note below)
                "geometry": feat["geometry"]["coordinates"],
            }
        )
    return feats


def compute_spatial_features(loc_lat, loc_lon, landslide_features, radius_km):
    nearest_km = None
    within_radius = []
    is_inside_any = False

    for lf in landslide_features:
        d = haversine_km(loc_lat, loc_lon, lf["lat"], lf["lon"])
        if nearest_km is None or d < nearest_km:
            nearest_km = d
        if d <= radius_km:
            within_radius.append(lf)
        if not is_inside_any:
            if point_in_multipolygon(loc_lon, loc_lat, lf["geometry"]):
                is_inside_any = True

    density_nearby = len(within_radius)
    area_nearby = sum((lf["area"] or 0) for lf in within_radius)

    return {
        "nearest_landslide_distance_km": round(nearest_km, 4) if nearest_km is not None else None,
        "spatial_landslide_presence": int(is_inside_any),
        "landslide_density_nearby": density_nearby,
        "historical_landslide_area_nearby": round(area_nearby, 4),
    }


def main():
    # ---- backup the master CSV before touching it ----
    shutil.copyfile(MASTER_CSV, BACKUP_CSV)
    print(f"Backed up {MASTER_CSV} -> {BACKUP_CSV}")

    master_df = pd.read_csv(MASTER_CSV)

    # ---- is_landslide_day: unchanged logic from the original script ----
    if "is_landslide_day" in master_df.columns:
        master_df = master_df.drop(columns=["is_landslide_day"])

    events_df = pd.DataFrame(documented_events)
    events_df["is_landslide_day"] = 1

    master_df = master_df.merge(
        events_df[["location", "date", "is_landslide_day"]],
        on=["location", "date"],
        how="left",
    )
    master_df["is_landslide_day"] = master_df["is_landslide_day"].fillna(0).astype(int)

    # ---- Bhuvan-derived spatial hazard features ----
    print(f"\nLoading Bhuvan landslide inventory from {GEOJSON_PATH} ...")
    landslide_features = load_landslide_features(GEOJSON_PATH)
    print(f"Loaded {len(landslide_features)} landslide polygon features.")

    # One (lat, lon) per location - reuse the location's own lat/lon rather
    # than recomputing, since master_df already carries fixed per-location
    # coordinates for all 122 daily rows of that location.
    unique_locations = master_df[["location", "lat", "lon"]].drop_duplicates()

    print(f"\nComputing spatial features for {len(unique_locations)} locations "
          f"(radius = {RADIUS_KM} km) ...")
    per_location_features = {}
    for _, row in unique_locations.iterrows():
        feats = compute_spatial_features(row["lat"], row["lon"], landslide_features, RADIUS_KM)
        per_location_features[row["location"]] = feats
        print(f"  {row['location']:<12} "
              f"nearest={feats['nearest_landslide_distance_km']:>8.3f} km | "
              f"inside_polygon={feats['spatial_landslide_presence']} | "
              f"density(<= {RADIUS_KM:.0f}km)={feats['landslide_density_nearby']:>3d} | "
              f"area_nearby={feats['historical_landslide_area_nearby']:.2f}")

    spatial_df = pd.DataFrame.from_dict(per_location_features, orient="index").reset_index()
    spatial_df = spatial_df.rename(columns={"index": "location"})

    merged = master_df.merge(spatial_df, on="location", how="left")
    merged.to_csv(MASTER_CSV, index=False)

    print(f"\nSaved updated {MASTER_CSV}")
    print(f"Total rows: {len(merged)}")
    print(f"Columns ({len(merged.columns)}): {merged.columns.tolist()}")
    print(f"\nPositive (landslide) days: {merged['is_landslide_day'].sum()}")
    print(f"Negative (no reported event) days: {(merged['is_landslide_day'] == 0).sum()}")
    print("\nNOTE: this is a very small, imbalanced label set (1 documented positive).")
    print("This is expected for an MVP without full Bhuvan/COOLR access - flag this")
    print("limitation clearly in your presentation as a known data constraint,")
    print("and mention Phase 2 would use the full ISRO-GSI inventory once available.")

    print("\nPer-location spatial hazard features (one row per location, "
          "identical across that location's daily rows):")
    print(spatial_df.to_string(index=False))

    print("\nAPPROXIMATIONS / DATA-QUALITY NOTES (geopandas/shapely unavailable, "
          "no network access in this environment):")
    print("  1. nearest_landslide_distance_km / density / area use each landslide")
    print("     polygon's provided Latitude/Longitude property as its representative")
    print("     point (verified to match the polygon's vertex-average centroid),")
    print("     not the true nearest edge of the polygon. For polygons this small")
    print("     (tens-hundreds of meters) relative to a 10 km radius, this is a")
    print("     reasonable approximation, but it is an approximation.")
    print("  2. spatial_landslide_presence uses an exact ray-casting point-in-polygon")
    print("     test against the real polygon rings (not radius-based), but treats")
    print("     (lon, lat) as planar coordinates rather than using a projected CRS.")
    print("     Negligible error at this polygon scale, but noted for transparency.")
    print("  3. historical_landslide_area_nearby sums the 'Area' property exactly as")
    print("     provided in the source data; units were not independently verified")
    print("     against Length x Width in this script (they appear broadly consistent")
    print("     but were not re-derived from geometry).")
    print("  4. is_landslide_day was NOT touched by the Bhuvan data (per design decision:")
    print("     Bhuvan Year=2023 records cannot be mapped to daily dates in the 2024")
    print("     June-Sept window, so they are used only as spatial/historical features).")


if __name__ == "__main__":
    main()
