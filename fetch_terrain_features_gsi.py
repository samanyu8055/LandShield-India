"""
fetch_terrain_features_gsi.py

Adds elevation_m and slope_deg to every positive (GSI dated event) and
pseudo-negative (background) sample.

METHOD (AWS Terrain Tiles — no per-call API limit)
----------------------------------------------------
OpenTopography's globaldem endpoint caps free API keys at 50 calls/24h,
which cannot cover ~6,705 India-wide points. This version instead pulls
from the public "Terrain Tiles" dataset on AWS Open Data
(s3://elevation-tiles-prod, mirrored at
https://s3.amazonaws.com/elevation-tiles-prod/geotiff/{z}/{x}/{y}.tif) —
real SRTM/ASTER/other-source elevation, keyless, no rate limit, served
as standard XYZ slippy-map GeoTIFF tiles (Float32 meters, Web Mercator).

Points are grouped by the tile they fall in at ZOOM_LEVEL=12 (~256x256px,
~38m/pixel, ~9.4km across at Indian latitudes) — one tile download covers
every point inside it, collapsing ~6,705 points into a few hundred tile
requests. Elevation is sampled per point; slope is computed locally via
a numpy gradient over each tile (converted from Web Mercator projected
distance to approximate true ground distance via a cos(latitude)
correction), same approach as the original script.

Tile downloads run concurrently (thread pool) since this is a network-
bound workload and the source has no meaningful rate limit.

OUTPUT FORMAT / CACHE / RESUME — UNCHANGED
--------------------------------------------
- data/gsi/gsi_terrain_features.csv keeps the same columns:
  latitude, longitude, elevation_m, slope_deg, terrain_status
- Tiles are cached at data/gsi/cache/terrain/tile_z<z>_x<x>_y<y>.tif and
  reused if present.
- On restart, points already present in the output CSV are skipped.

NO FABRICATION: any point whose tile can't be fetched after retries, or
whose pixel is nodata / off-land, is written with status="failed" and
NaN elevation/slope — never estimated, interpolated, or backfilled from
a neighboring point.
"""

import math
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import numpy as np
import pandas as pd
import requests

POS_FILE = Path("data/gsi/gsi_dated_environmental_features.csv")
NEG_FILE = Path("data/gsi/gsi_pseudo_negative_samples.csv")

CACHE_DIR = Path("data/gsi/cache/terrain")
OUTPUT_FILE = Path("data/gsi/gsi_terrain_features.csv")

TILE_BASE_URL = "https://s3.amazonaws.com/elevation-tiles-prod/geotiff/{z}/{x}/{y}.tif"
ZOOM_LEVEL = 12            # ~38m/pixel at these latitudes, closest match to prior SRTM-30m use
MAX_WORKERS = 8            # concurrent tile downloads (S3, no per-key rate limit)
REQUEST_TIMEOUT_SECONDS = 30
MAX_RETRIES = 3
RETRY_BACKOFF_SECONDS = 3

OUT_COLUMNS = ["latitude", "longitude", "elevation_m", "slope_deg", "terrain_status"]

write_lock = threading.Lock()


def load_unique_points() -> pd.DataFrame:
    pos = pd.read_csv(POS_FILE)
    neg = pd.read_csv(NEG_FILE)
    pts = pd.concat(
        [pos[["Latitude", "Longitude"]], neg[["Latitude", "Longitude"]]],
        ignore_index=True,
    ).rename(columns={"Latitude": "latitude", "Longitude": "longitude"})
    pts = pts.dropna().drop_duplicates().reset_index(drop=True)
    pts["latitude"] = pts["latitude"].round(5)
    pts["longitude"] = pts["longitude"].round(5)
    return pts


def load_done_keys() -> set:
    if OUTPUT_FILE.exists():
        done = pd.read_csv(OUTPUT_FILE)
        ok = done[done["terrain_status"] == "ok"]
        return set(zip(ok["latitude"].round(5), ok["longitude"].round(5)))
    return set()


def deg2tile(lat_deg: float, lon_deg: float, zoom: int):
    lat_rad = math.radians(lat_deg)
    n = 2.0 ** zoom
    xtile = int((lon_deg + 180.0) / 360.0 * n)
    ytile = int((1.0 - math.log(math.tan(lat_rad) + 1 / math.cos(lat_rad)) / math.pi) / 2.0 * n)
    return xtile, ytile


def assign_tiles(points: pd.DataFrame) -> dict:
    """Group points by (x, y) slippy tile at ZOOM_LEVEL -> list of (lat, lon)."""
    tiles = {}
    for lat, lon in zip(points["latitude"], points["longitude"]):
        x, y = deg2tile(lat, lon, ZOOM_LEVEL)
        tiles.setdefault((x, y), []).append((lat, lon))
    return tiles


def download_tile(tile_key) -> Path | None:
    x, y = tile_key
    tile_path = CACHE_DIR / f"tile_z{ZOOM_LEVEL}_x{x}_y{y}.tif"
    if tile_path.exists() and tile_path.stat().st_size > 0:
        return tile_path

    url = TILE_BASE_URL.format(z=ZOOM_LEVEL, x=x, y=y)

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = requests.get(url, timeout=REQUEST_TIMEOUT_SECONDS)
        except requests.exceptions.RequestException as exc:
            print(f"  [tile {x},{y}] request exception (attempt {attempt}): {exc}")
            import time
            time.sleep(RETRY_BACKOFF_SECONDS * attempt)
            continue

        if resp.status_code == 200 and resp.content:
            CACHE_DIR.mkdir(parents=True, exist_ok=True)
            tmp_path = tile_path.with_suffix(".tif.part")
            tmp_path.write_bytes(resp.content)
            tmp_path.rename(tile_path)
            return tile_path

        if resp.status_code == 404:
            # No tile at this location (e.g. genuinely off-coverage) — not
            # worth retrying, but still a real "no data" outcome, not fabricated.
            print(f"  [tile {x},{y}] HTTP 404 (no tile at this location)")
            return None

        print(f"  [tile {x},{y}] HTTP {resp.status_code} (attempt {attempt}): {resp.text[:150]}")
        import time
        time.sleep(RETRY_BACKOFF_SECONDS * attempt)

    return None


def sample_points_from_tile(tile_path: Path, tile_points):
    """Returns list of (lat, lon, elevation_m, slope_deg, status)."""
    import rasterio

    results = []
    with rasterio.open(tile_path) as src:
        elevation = src.read(1).astype(float)
        nodata = src.nodata
        if nodata is not None:
            elevation[elevation == nodata] = np.nan

        transform = src.transform
        px_size_x = transform.a   # projected (Web Mercator) meters/pixel
        px_size_y = -transform.e

        mean_lat = float(np.mean([p[0] for p in tile_points]))
        # Web Mercator overstates true ground distance by 1/cos(lat);
        # correct back to approximate true meters (same style of
        # approximation as the original DEM/slope script).
        scale = math.cos(math.radians(mean_lat))
        dx = px_size_x * scale
        dy = px_size_y * scale

        gy, gx = np.gradient(elevation, dy, dx)
        slope_deg = np.degrees(np.arctan(np.sqrt(gx**2 + gy**2)))

        for lat, lon in tile_points:
            try:
                # reproject point lon/lat -> tile's CRS (Web Mercator) for indexing
                from rasterio.warp import transform as warp_transform
                xs, ys = warp_transform("EPSG:4326", src.crs, [lon], [lat])
                row, col = src.index(xs[0], ys[0])
                elev_val = elevation[row, col]
                slope_val = slope_deg[row, col]
                if row < 0 or col < 0 or row >= elevation.shape[0] or col >= elevation.shape[1] or np.isnan(elev_val):
                    results.append((lat, lon, np.nan, np.nan, "failed"))
                else:
                    results.append((lat, lon, round(float(elev_val), 1), round(float(slope_val), 2), "ok"))
            except Exception:
                results.append((lat, lon, np.nan, np.nan, "failed"))
    return results


def process_tile(tile_key, tile_points):
    tile_path = download_tile(tile_key)
    if tile_path is None:
        return [(lat, lon, np.nan, np.nan, "failed") for lat, lon in tile_points]
    try:
        return sample_points_from_tile(tile_path, tile_points)
    except Exception as exc:
        print(f"  [tile {tile_key}] parse error: {exc}")
        return [(lat, lon, np.nan, np.nan, "failed") for lat, lon in tile_points]


def main():
    points = load_unique_points()
    done_keys = load_done_keys()

    if not OUTPUT_FILE.exists():
        OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
        pd.DataFrame(columns=OUT_COLUMNS).to_csv(OUTPUT_FILE, index=False)

    all_tiles = assign_tiles(points)
    pending_tiles = {}
    for key, pts in all_tiles.items():
        pending = [p for p in pts if p not in done_keys]
        if pending:
            pending_tiles[key] = pending

    total_points = len(points)
    total_pending_points = sum(len(v) for v in pending_tiles.values())
    print(f"Unique points total: {total_points}")
    print(f"Already done (resume): {len(done_keys)}")
    print(f"Tiles with pending points: {len(pending_tiles)}  (of {len(all_tiles)} total tiles, zoom={ZOOM_LEVEL})")
    print(f"Points remaining: {total_pending_points}")
    print(f"Concurrency: {MAX_WORKERS} workers\n")

    n_ok, n_fail, tiles_done = 0, 0, 0
    total_tiles = len(pending_tiles)
    failed_points = []

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {
            executor.submit(process_tile, key, pts): key
            for key, pts in pending_tiles.items()
        }
        for future in as_completed(futures):
            key = futures[future]
            try:
                results = future.result()
            except Exception as exc:
                print(f"  [tile {key}] unexpected error: {exc}")
                results = [(lat, lon, np.nan, np.nan, "failed") for lat, lon in pending_tiles[key]]

            ok = sum(1 for r in results if r[4] == "ok")
            fail = sum(1 for r in results if r[4] == "failed")
            n_ok += ok
            n_fail += fail
            tiles_done += 1
            failed_points.extend((r[0], r[1]) for r in results if r[4] == "failed")

            with write_lock:
                pd.DataFrame(results, columns=OUT_COLUMNS).to_csv(
                    OUTPUT_FILE, mode="a", header=False, index=False
                )

            print(f"  [tile {tiles_done}/{total_tiles}] key={key} pts={len(results)} "
                  f"ok={ok} failed={fail}  | cumulative ok={n_ok} failed={n_fail}")

    print("\nDone.")
    print(f"Newly fetched OK: {n_ok}")
    print(f"Newly failed:     {n_fail}")
    if failed_points:
        print(f"\nFailed points this run ({len(failed_points)}):")
        for lat, lon in failed_points[:50]:
            print(f"  {lat}, {lon}")
        if len(failed_points) > 50:
            print(f"  ... and {len(failed_points) - 50} more (see terrain_status='failed' rows in output CSV)")
        print("Re-run this script to retry failed points (resume-safe).")
    print(f"Output: {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
