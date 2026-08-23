"""
fetch_ndvi_gsi.py

Adds ndvi_mean to every positive (GSI dated event) and pseudo-negative
(background) sample.

METHOD
------
NDVI is computed as the mean Sentinel-2 (COPERNICUS/S2_SR_HARMONIZED)
NDVI over the PRE-EVENT window (event date - PRE_EVENT_WINDOW_DAYS) to
(event date - 1 day), cloud-masked via the SCL band. Using a strictly
pre-event window avoids leaking post-slide bare-earth signal into a
feature meant to represent vegetation cover BEFORE the slide, and avoids
using future information for pseudo-negatives too (same convention is
applied to both classes for consistency).

Every sample has its own date, so this is fetched per-record (not just
per unique coordinate) — the same location can have a different NDVI
window depending on which date it belongs to.

CACHING / RESUME
-----------------
- Results are appended to data/gsi/gsi_ndvi_features.csv keyed by
  record_id, as they complete.
- On restart, record_ids already present are skipped.
- A record that fails (cloud cover, no S2 coverage, no EE image, etc.)
  is recorded with status="failed" and ndvi_mean=NaN — never fabricated
  or backfilled from a neighboring point.
"""

from pathlib import Path
from datetime import datetime, timedelta

import pandas as pd

POS_FILE = Path("data/gsi/gsi_dated_environmental_features.csv")
NEG_FILE = Path("data/gsi/gsi_pseudo_negative_samples.csv")
OUTPUT_FILE = Path("data/gsi/gsi_ndvi_features.csv")

EE_PROJECT = "sih-landslide-project"
PRE_EVENT_WINDOW_DAYS = 60
MAX_CLOUD_PCT = 40

OUT_COLUMNS = ["record_id", "latitude", "longitude", "date", "ndvi_mean", "ndvi_status"]


def load_combined_samples() -> pd.DataFrame:
    pos = pd.read_csv(POS_FILE)[["Slide_No", "Latitude", "Longitude", "event_date"]].rename(
        columns={"Slide_No": "record_id", "Latitude": "latitude", "Longitude": "longitude", "event_date": "date"}
    )
    neg = pd.read_csv(NEG_FILE)[["record_id", "Latitude", "Longitude", "date"]].rename(
        columns={"Latitude": "latitude", "Longitude": "longitude"}
    )
    combined = pd.concat([pos, neg], ignore_index=True)
    combined = combined.dropna(subset=["record_id", "latitude", "longitude", "date"])
    return combined


def load_done_ids() -> set:
    if OUTPUT_FILE.exists():
        done = pd.read_csv(OUTPUT_FILE)
        ok = done[done["ndvi_status"] == "ok"]
        return set(ok["record_id"].astype(str))
    return set()


def mask_clouds(image, ee):
    scl = image.select("SCL")
    mask = scl.neq(3).And(scl.neq(8)).And(scl.neq(9)).And(scl.neq(10)).And(scl.neq(11))
    return image.updateMask(mask)


SENTINEL2_LAUNCH_DATE = datetime(2015, 6, 23)  # COPERNICUS/S2_SR_HARMONIZED has no data before this


def fetch_ndvi_for_record(ee, lat, lon, date_str):
    """
    Returns (ndvi_val_or_None, reason_str). reason_str is only for console
    logging clarity — it is never written to the output CSV, so the output
    schema stays exactly as before.
    """
    end = datetime.strptime(date_str, "%Y-%m-%d")
    start = end - timedelta(days=PRE_EVENT_WINDOW_DAYS)

    # Cheap pre-check: Sentinel-2 has zero coverage before its launch date.
    # Skipping this avoids a wasted EE call and gives a clear, honest reason
    # instead of a generic failure.
    if end < SENTINEL2_LAUNCH_DATE:
        return None, "pre-dates Sentinel-2 launch (2015-06-23) — no possible coverage"

    geom = ee.Geometry.Point([lon, lat])
    collection = (
        ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
        .filterDate(start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d"))
        .filterBounds(geom)
        .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", MAX_CLOUD_PCT))
        .map(lambda img: mask_clouds(img, ee))
    )

    def add_ndvi(image):
        ndvi = image.normalizedDifference(["B8", "B4"]).rename("NDVI")
        return image.addBands(ndvi)

    with_ndvi = collection.map(add_ndvi)
    mean_ndvi_image = with_ndvi.select("NDVI").mean()

    # BUG FIX: when the filtered collection has zero matching images (no
    # cloud-free Sentinel-2 pass in this window), .mean() on an empty
    # ImageCollection returns a zero-band image, so reduceRegion() returns
    # an EMPTY dictionary — it never contains an "NDVI" key. Calling
    # .get("NDVI") directly throws "Dictionary does not contain key: 'NDVI'"
    # server-side, and a default-value .get("NDVI", None) did not reliably
    # suppress that either. Fix: explicitly check reduced.contains("NDVI")
    # first (a real, synchronous EE call), and only call .get("NDVI") when
    # the key is actually present — otherwise return None with a clear
    # reason, never calling .get() on a dictionary that lacks the key.
    reduced = mean_ndvi_image.reduceRegion(
        reducer=ee.Reducer.mean(), geometry=geom, scale=10, maxPixels=1e9
    )

    has_ndvi = reduced.contains("NDVI").getInfo()
    if not has_ndvi:
        return None, "no NDVI band/result (empty reduceRegion dictionary)"

    ndvi_val = reduced.get("NDVI").getInfo()
    if ndvi_val is None:
        return None, "no cloud-free Sentinel-2 imagery in the pre-event window"
    return round(ndvi_val, 4), "ok"


def main():
    import ee

    try:
        ee.Initialize(project=EE_PROJECT)
    except Exception as exc:
        print(f"FATAL: could not initialize Earth Engine ({exc}). "
              f"Authenticate with `earthengine authenticate` and re-run.")
        return

    samples = load_combined_samples()
    done_ids = load_done_ids()
    todo = samples[~samples["record_id"].astype(str).isin(done_ids)]

    print(f"Total samples: {len(samples)}")
    print(f"Already cached (resume): {len(done_ids)}")
    print(f"Remaining to fetch: {len(todo)}")

    if not OUTPUT_FILE.exists():
        OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
        pd.DataFrame(columns=OUT_COLUMNS).to_csv(OUTPUT_FILE, index=False)

    n_ok, n_fail = 0, 0
    failure_log = []  # (record_id, reason) — for the end-of-run summary only
    for i, row in enumerate(todo.itertuples(), start=1):
        try:
            ndvi_val, reason = fetch_ndvi_for_record(ee, row.latitude, row.longitude, str(row.date)[:10])
            status = "ok" if ndvi_val is not None else "failed"
            if status == "ok":
                n_ok += 1
            else:
                n_fail += 1
                failure_log.append((row.record_id, reason))
        except Exception as exc:
            print(f"    [{row.record_id}] error: {exc}")
            ndvi_val, status = None, "failed"
            n_fail += 1
            failure_log.append((row.record_id, f"exception: {exc}"))

        pd.DataFrame(
            [[row.record_id, row.latitude, row.longitude, row.date, ndvi_val, status]],
            columns=OUT_COLUMNS,
        ).to_csv(OUTPUT_FILE, mode="a", header=False, index=False)

        if i % 100 == 0 or i == len(todo):
            print(f"  [{i}/{len(todo)}] ok={n_ok} failed={n_fail}")

    print("\nDone.")
    print(f"Newly fetched OK: {n_ok}")
    print(f"Newly failed:     {n_fail}")
    if failure_log:
        print(f"\nFailure reasons this run ({len(failure_log)}):")
        for record_id, reason in failure_log[:50]:
            print(f"  [{record_id}] {reason}")
        if len(failure_log) > 50:
            print(f"  ... and {len(failure_log) - 50} more (all recorded as ndvi_status='failed' in the output CSV)")
        print("Re-run this script to retry failed points (resume-safe) — points with a "
              "pre-Sentinel-2 date will always fail, since no coverage exists for them.")
    print(f"Output: {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
