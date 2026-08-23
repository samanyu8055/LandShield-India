"""
build_india_environmental_features.py

Attaches historical environmental conditions (rainfall + soil moisture) to the
REAL, DATED GSI landslide events. Does nothing else.

INPUT:
    data/gsi/gsi_dated_events.csv
        The 2,242 GSI records that have a genuine full occurrence date
        (NOT the year-only inventory - that file is never touched here).

OUTPUT:
    data/gsi/gsi_dated_environmental_features.csv
        Every original input column, unchanged, plus:
            event_date, event_year, event_month, landslide_event,
            rainfall_mm, rainfall_3day_mm, soil_moisture

DATA SOURCE (verified 2026-08-23 against the live Open-Meteo docs at
https://open-meteo.com/en/docs/historical-weather-api before writing this
script - do not change these parameter names without re-checking that page):
    Open-Meteo Historical Weather API - /v1/archive
    Reanalysis (ERA5 / ERA5-Land / IFS "Best Match", data from 1940-present).
    Daily variables used (current, documented names):
        precipitation_sum               (mm, daily sum)
        soil_moisture_0_to_7cm_mean     (m3/m3, daily mean of the 0-7cm layer)
    timezone=Asia/Kolkata (daily aggregation requires a timezone; matches the
    existing fetch_rainfall.py convention for this project).
    This matches the exact daily variables already used successfully by the
    existing, untouched fetch_rainfall.py.

WHY BATCHED BY DATE:
    The current API documentation confirms &latitude=/&longitude= accept
    comma-separated lists for multiple locations in a SINGLE request, but
    &start_date=/&end_date= are shared across the whole request. So this
    script groups events by their exact event_date and batches the distinct
    locations that share a date into one request per batch (see
    LOCATIONS_PER_BATCH), rather than 2,242 independent single-location
    requests.

CACHING / RESUME:
    Every successfully fetched (lat, lon, event_date) result is written to a
    local JSON cache (CACHE_PATH) immediately after each batch. On any rerun,
    already-cached keys are skipped entirely - only missing/failed keys are
    re-requested. Only successes are cached, so a failed batch is always
    retried on the next run without any separate "resume state" needed.

DATA HONESTY:
    - No rainfall/soil-moisture value is ever invented. If the API can't
      provide a value (error, no coverage, date out of range), the output
      cell is left blank (NaN) and counted in the validation report.
    - rainfall_3day_mm is only computed when all 3 days in the window
      (event_date-2 .. event_date) are present; a partial sum is never
      silently reported as a full 3-day accumulation.
    - This script does not create labels, does not sample negatives, does
      not train anything, and does not touch train_model.py,
      compute_hybrid_risk.py, or any other protected file.
"""

import json
import math
import os
import time
from datetime import timedelta

import pandas as pd
import requests

# --------------------------------------------------------------------------
# CONFIG
# --------------------------------------------------------------------------
INPUT_CSV = "data/gsi/gsi_dated_events.csv"
OUTPUT_CSV = "data/gsi/gsi_dated_environmental_features.csv"
CACHE_PATH = "data/gsi/cache/openmeteo_env_cache.json"

ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
DAILY_VARS = "precipitation_sum,soil_moisture_0_to_7cm_mean"
TIMEZONE = "Asia/Kolkata"

ROLLING_WINDOW_DAYS = 3          # event_date - 2 .. event_date, inclusive
COORD_ROUND_DECIMALS = 4         # ~11m precision - far finer than the weather
                                  # grid cell (9-25km), used only as a stable
                                  # cache/request key, not to alter the data.

LOCATIONS_PER_BATCH = 40         # self-imposed safe chunk size, not a
                                  # documented Open-Meteo hard limit.
REQUEST_TIMEOUT_SECONDS = 30
MAX_RETRIES_PER_BATCH = 4
RETRY_BACKOFF_BASE_SECONDS = 3   # 3, 6, 12, 24 ...
DELAY_BETWEEN_BATCHES_SECONDS = 1.2  # conservative, self-imposed rate limit
SAVE_EVERY_N_BATCHES = 5         # flush cache + write intermediate output

# ERA5/ERA5-Land coverage starts 1940; the archive typically lags a few days
# behind "today" (ERA5 ~5 day delay per Open-Meteo docs). Dates outside this
# window are reported as out-of-coverage rather than requested.
EARLIEST_SUPPORTED_DATE = pd.Timestamp("1940-01-01")

# Rough India bounding box, used only to flag obviously invalid coordinates
# for the validation report - never used to alter or drop data silently.
INDIA_LAT_RANGE = (6.0, 38.0)
INDIA_LON_RANGE = (68.0, 98.0)

# Candidate column-name aliases, since this script has not been run against
# the real gsi_dated_events.csv and must not assume an exact schema.
COLUMN_ALIASES = {
    "slide_no": ["Slide_No", "slide_no", "SlideNo", "Slide No", "ID", "id"],
    "state": ["State", "state", "State/UT", "state_ut"],
    "district": ["District", "district"],
    "slide_name": ["Slide_Name", "slide_name", "Landslide_Name", "Name", "name"],
    "latitude": ["Latitude", "latitude", "lat", "Lat"],
    "longitude": ["Longitude", "longitude", "lon", "lng", "Lon"],
    "occurrence_date": ["Occurrence_Date", "occurrence_date", "Date", "date", "Event_Date"],
    "occurrence_year": ["Occurrence_Year", "occurrence_year", "Year", "year"],
}


def find_column(df, key, required=True):
    for cand in COLUMN_ALIASES[key]:
        if cand in df.columns:
            return cand
    if required:
        raise SystemExit(
            f"\nFATAL: could not find a column for '{key}' in {INPUT_CSV}.\n"
            f"Looked for any of: {COLUMN_ALIASES[key]}\n"
            f"Actual columns present: {df.columns.tolist()}\n"
            f"Refusing to guess - fix the alias list above or rename the column, then rerun."
        )
    return None


# --------------------------------------------------------------------------
# CACHE
# --------------------------------------------------------------------------
def load_cache():
    if os.path.exists(CACHE_PATH):
        with open(CACHE_PATH) as f:
            return json.load(f)
    return {}


def save_cache(cache):
    os.makedirs(os.path.dirname(CACHE_PATH), exist_ok=True)
    tmp_path = CACHE_PATH + ".tmp"
    with open(tmp_path, "w") as f:
        json.dump(cache, f)
    os.replace(tmp_path, CACHE_PATH)  # atomic-ish, avoids truncated cache on crash


def cache_key(lat, lon, event_date_str):
    return f"{round(lat, COORD_ROUND_DECIMALS)}|{round(lon, COORD_ROUND_DECIMALS)}|{event_date_str}"


# --------------------------------------------------------------------------
# FETCH
# --------------------------------------------------------------------------
def fetch_batch(locations, event_date):
    """
    locations: list of (lat, lon) tuples sharing the same event_date.
    Returns: dict {(lat, lon): {"rainfall_mm":..., "rainfall_3day_mm":..., "soil_moisture":...}}
             Only successfully parsed locations are included. Never fabricates.
    """
    start_date = (event_date - timedelta(days=ROLLING_WINDOW_DAYS - 1)).strftime("%Y-%m-%d")
    end_date = event_date.strftime("%Y-%m-%d")

    lat_str = ",".join(str(round(lat, COORD_ROUND_DECIMALS)) for lat, lon in locations)
    lon_str = ",".join(str(round(lon, COORD_ROUND_DECIMALS)) for lat, lon in locations)

    params = {
        "latitude": lat_str,
        "longitude": lon_str,
        "start_date": start_date,
        "end_date": end_date,
        "daily": DAILY_VARS,
        "timezone": TIMEZONE,
    }

    last_error = None
    for attempt in range(1, MAX_RETRIES_PER_BATCH + 1):
        try:
            resp = requests.get(ARCHIVE_URL, params=params, timeout=REQUEST_TIMEOUT_SECONDS)
        except requests.exceptions.RequestException as exc:
            last_error = f"request exception: {exc}"
            time.sleep(RETRY_BACKOFF_BASE_SECONDS * attempt)
            continue

        if resp.status_code == 400:
            # Bad parameter / unsupported date etc. - not retryable, don't fabricate.
            print(f"    [HTTP 400, not retrying] {resp.text[:200]}")
            return {}

        if resp.status_code != 200:
            last_error = f"HTTP {resp.status_code}: {resp.text[:200]}"
            time.sleep(RETRY_BACKOFF_BASE_SECONDS * attempt)
            continue

        try:
            payload = resp.json()
        except ValueError as exc:
            last_error = f"JSON decode error: {exc}"
            time.sleep(RETRY_BACKOFF_BASE_SECONDS * attempt)
            continue

        # Single location -> dict. Multiple locations -> list of dicts
        # (confirmed in current Open-Meteo docs).
        if isinstance(payload, dict):
            payload_list = [payload]
        else:
            payload_list = payload

        results = {}
        for (lat, lon), entry in zip(locations, payload_list):
            if "error" in entry and entry.get("error"):
                continue  # this location failed; leave it out, do not fabricate
            daily = entry.get("daily", {})
            times = daily.get("time", [])
            precip = daily.get("precipitation_sum", [])
            soil = daily.get("soil_moisture_0_to_7cm_mean", [])

            if end_date not in times:
                continue
            event_idx = times.index(end_date)

            same_day_rain = precip[event_idx] if event_idx < len(precip) else None
            same_day_soil = soil[event_idx] if event_idx < len(soil) else None

            # 3-day accumulation only if all 3 days actually have a value.
            if len(precip) >= ROLLING_WINDOW_DAYS and all(
                v is not None for v in precip[:ROLLING_WINDOW_DAYS]
            ):
                rain_3day = round(sum(precip[:ROLLING_WINDOW_DAYS]), 2)
            else:
                rain_3day = None

            results[(lat, lon)] = {
                "rainfall_mm": same_day_rain,
                "rainfall_3day_mm": rain_3day,
                "soil_moisture": same_day_soil,
            }
        return results

    print(f"    [FAILED after {MAX_RETRIES_PER_BATCH} attempts] {last_error}")
    return {}


# --------------------------------------------------------------------------
# MAIN
# --------------------------------------------------------------------------
def main():
    if not os.path.exists(INPUT_CSV):
        raise SystemExit(
            f"\nFATAL: input file not found: {INPUT_CSV}\n"
            f"This script does not fabricate data - nothing was written.\n"
            f"Run this from the project root, after gsi_dated_events.csv exists."
        )

    df = pd.read_csv(INPUT_CSV)
    print(f"Loaded {INPUT_CSV}: {len(df)} rows, {len(df.columns)} columns")
    print(f"Columns found: {df.columns.tolist()}\n")

    col_slide_no = find_column(df, "slide_no")
    col_state = find_column(df, "state")
    col_district = find_column(df, "district", required=False)
    col_slide_name = find_column(df, "slide_name", required=False)
    col_lat = find_column(df, "latitude")
    col_lon = find_column(df, "longitude")
    col_occ_date = find_column(df, "occurrence_date")
    col_occ_year = find_column(df, "occurrence_year", required=False)

    input_count = len(df)

    # ---- validation: duplicates, coordinate/date sanity (report only, never silently fix) ----
    dup_slide_no = df[col_slide_no].duplicated().sum()
    df["_lat_numeric"] = pd.to_numeric(df[col_lat], errors="coerce")
    df["_lon_numeric"] = pd.to_numeric(df[col_lon], errors="coerce")
    bad_coords = df["_lat_numeric"].isna() | df["_lon_numeric"].isna()
    out_of_india_bbox = (
        ~df["_lat_numeric"].between(*INDIA_LAT_RANGE)
        | ~df["_lon_numeric"].between(*INDIA_LON_RANGE)
    ) & ~bad_coords

    df["event_date"] = pd.to_datetime(df[col_occ_date], errors="coerce")
    bad_dates = df["event_date"].isna()
    df["event_year"] = df["event_date"].dt.year
    df["event_month"] = df["event_date"].dt.month
    df["landslide_event"] = 1  # every row in gsi_dated_events.csv is a real documented event

    print("Pre-fetch validation:")
    print(f"  Duplicate {col_slide_no} values: {dup_slide_no}")
    print(f"  Rows with non-numeric lat/lon: {int(bad_coords.sum())}")
    print(f"  Rows with coordinates outside a rough India bounding box: {int(out_of_india_bbox.sum())}")
    print(f"  Rows with unparseable {col_occ_date}: {int(bad_dates.sum())}")
    if col_occ_year:
        year_mismatch = (df["event_year"] != pd.to_numeric(df[col_occ_year], errors="coerce")).sum()
        print(f"  Rows where parsed event_year differs from {col_occ_year}: {int(year_mismatch)}")

    fetchable = df[~bad_coords & ~bad_dates & df["event_date"].ge(EARLIEST_SUPPORTED_DATE)].copy()
    unfetchable_count = len(df) - len(fetchable)
    if unfetchable_count:
        print(f"  {unfetchable_count} rows excluded from fetching (bad coords / bad date / before {EARLIEST_SUPPORTED_DATE.date()}) - kept in output with blank environmental columns.")
    print()

    # ---- build unique (date -> list of unique rounded coordinates) ----
    fetchable["_date_str"] = fetchable["event_date"].dt.strftime("%Y-%m-%d")
    fetchable["_lat_r"] = fetchable["_lat_numeric"].round(COORD_ROUND_DECIMALS)
    fetchable["_lon_r"] = fetchable["_lon_numeric"].round(COORD_ROUND_DECIMALS)

    cache = load_cache()
    print(f"Loaded cache: {len(cache)} previously-fetched (lat,lon,date) entries from {CACHE_PATH}\n" if cache else "No existing cache found - starting fresh.\n")

    unique_needed = (
        fetchable[["_date_str", "_lat_r", "_lon_r"]]
        .drop_duplicates()
    )
    unique_needed["_key"] = unique_needed.apply(
        lambda r: cache_key(r["_lat_r"], r["_lon_r"], r["_date_str"]), axis=1
    )
    still_needed = unique_needed[~unique_needed["_key"].isin(cache.keys())]

    print(f"Unique (location, date) pairs required: {len(unique_needed)}")
    print(f"Already cached (skipped): {len(unique_needed) - len(still_needed)}")
    print(f"Still to fetch this run: {len(still_needed)}\n")

    batches = []
    for date_str, group in still_needed.groupby("_date_str"):
        coords = list(zip(group["_lat_r"], group["_lon_r"]))
        for i in range(0, len(coords), LOCATIONS_PER_BATCH):
            batches.append((date_str, coords[i:i + LOCATIONS_PER_BATCH]))

    print(f"Batches to run: {len(batches)} (up to {LOCATIONS_PER_BATCH} locations/date per batch)\n")

    for i, (date_str, coords) in enumerate(batches, start=1):
        event_date = pd.Timestamp(date_str)
        print(f"[{i}/{len(batches)}] date={date_str} locations={len(coords)}")
        result = fetch_batch(coords, event_date)
        for (lat, lon), vals in result.items():
            cache[cache_key(lat, lon, date_str)] = vals
        print(f"    -> {len(result)}/{len(coords)} locations succeeded")

        if i % SAVE_EVERY_N_BATCHES == 0 or i == len(batches):
            save_cache(cache)
            print(f"    (cache saved: {len(cache)} total entries)")

        time.sleep(DELAY_BETWEEN_BATCHES_SECONDS)

    save_cache(cache)

    # ---- join cache back onto every row (including originally-unfetchable ones, which get NaN) ----
    def lookup(row):
        if pd.isna(row["event_date"]) or pd.isna(row["_lat_numeric"]) or pd.isna(row["_lon_numeric"]):
            return pd.Series({"rainfall_mm": None, "rainfall_3day_mm": None, "soil_moisture": None})
        key = cache_key(row["_lat_numeric"], row["_lon_numeric"], row["event_date"].strftime("%Y-%m-%d"))
        vals = cache.get(key)
        if vals is None:
            return pd.Series({"rainfall_mm": None, "rainfall_3day_mm": None, "soil_moisture": None})
        return pd.Series(vals)

    env = df.apply(lookup, axis=1)
    df["rainfall_mm"] = env["rainfall_mm"]
    df["rainfall_3day_mm"] = env["rainfall_3day_mm"]
    df["soil_moisture"] = env["soil_moisture"]

    df = df.drop(columns=["_lat_numeric", "_lon_numeric"])

    os.makedirs(os.path.dirname(OUTPUT_CSV), exist_ok=True)
    df.to_csv(OUTPUT_CSV, index=False)

    # ---- final validation report ----
    print("\n" + "=" * 70)
    print("FINAL VALIDATION REPORT")
    print("=" * 70)
    print(f"Input event count:                {input_count}")
    print(f"Successful environmental matches:  {df['rainfall_mm'].notna().sum()} (rainfall_mm present)")
    print(f"Failed matches (no rainfall_mm):   {df['rainfall_mm'].isna().sum()}")
    print(f"Missing rainfall_mm:               {df['rainfall_mm'].isna().sum()}")
    print(f"Missing rainfall_3day_mm:          {df['rainfall_3day_mm'].isna().sum()}")
    print(f"Missing soil_moisture:             {df['soil_moisture'].isna().sum()}")
    valid_dates = df["event_date"].dropna()
    if len(valid_dates):
        print(f"Min event date:                    {valid_dates.min().date()}")
        print(f"Max event date:                    {valid_dates.max().date()}")
    print(f"Unique states ({col_state}):        {df[col_state].nunique()}")
    print(f"Duplicate {col_slide_no}:                {int(df[col_slide_no].duplicated().sum())}")
    non_numeric_rainfall = pd.to_numeric(df["rainfall_mm"], errors="coerce").isna() & df["rainfall_mm"].notna()
    print(f"Non-numeric rainfall_mm values:    {int(non_numeric_rainfall.sum())}")

    print("\nSample output rows:")
    sample_cols = [c for c in [col_slide_no, col_state, col_district, "event_date", "event_year",
                                "event_month", "landslide_event", "rainfall_mm", "rainfall_3day_mm",
                                "soil_moisture"] if c and c in df.columns]
    print(df[sample_cols].head(10).to_string(index=False))

    print(f"\nSaved {OUTPUT_CSV}")
    print("\nNo synthetic values were generated. Missing environmental values are")
    print("left blank (NaN) in the output and are counted above, not invented.")
    print("This script does not train, score, or label anything beyond attaching")
    print("real environmental data to already-real, already-dated GSI events.")


if __name__ == "__main__":
    main()
