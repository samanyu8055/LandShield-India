"""
sample_pseudo_negatives.py

Generates PSEUDO-NEGATIVE / BACKGROUND candidate samples for the NER
landslide ML training dataset. Does nothing else.

THIS SCRIPT DOES NOT:
    - call Open-Meteo, OpenTopography, Sentinel/GEE, or any external API
    - compute rainfall, soil moisture, elevation, slope, or NDVI
    - build the final training table
    - train or evaluate any model
    - modify any existing CSV or Python file

WHAT "PSEUDO-NEGATIVE" MEANS (read before using this output):
    A location/date pair in the output that GSI has NOT recorded a
    landslide at. This is NOT a confirmed observation that no landslide
    occurred there. The GSI inventory is a field-validated but NOT
    exhaustive record - absence from GSI is absence of documentation,
    not proof of safety. Every row in the output is tagged
    source="pseudo_negative" for exactly this reason, and this caveat
    must be carried into any report, slide, or downstream model card
    that uses this file.

INPUTS (read-only, never modified):
    data/gsi/gsi_landslide_inventory_normalized.csv
        Complete normalized GSI inventory (35,716 records: dated,
        year-only, AND undated). Used ONLY as a spatial exclusion mask -
        every point in this file, regardless of date status, blocks a
        1 km radius around it. Year-only and undated records are never
        given a date and are never used as anything other than "a real
        landslide happened near here at some point."

    data/gsi/gsi_dated_events.csv
        The 2,242 positive events with genuine full dates. Used to:
          (a) count the number of positives (drives the negative target)
          (b) derive the empirical month distribution for negative dates
          (c) derive the study year range (min/max event_year)

STUDY REGION:
    The eight Northeast Region (NER) states, restricted to the actual
    footprint of GSI-surveyed points in each state (bounding box of that
    state's inventory coordinates, padded by NER_BBOX_PADDING_DEG). This
    is a deliberate, documented approximation: it reflects where GSI has
    actually surveyed in each state, not each state's full political
    boundary. Lowland/valley areas far from any surveyed point are not
    covered by this sampling region - this is reported as a limitation,
    not hidden.

NEGATIVE SAMPLING DESIGN (per approved parameters):
    - Spatial exclusion radius: 1 km from ANY point in the complete GSI
      inventory (dated + year-only + undated).
    - Negative:positive ratio target: 2:1 (≈ 2 x len(gsi_dated_events)).
    - Geographic stratification: quota split ~evenly across the 8 NER
      states (not proportional to GSI point density, so negatives are
      not concentrated only in the most heavily-surveyed/easy states),
      and within each state further stratified across a grid of
      sub-cells so negatives spread across that state's study region
      rather than clustering in one corner of it. NOTE: without slope/
      elevation data (fetched in a later, separate step) this script
      cannot stratify by terrain ruggedness - only by geographic
      spread. This is a known limitation of THIS step, not silently
      worked around.
    - Temporal assignment: each negative's YEAR is drawn uniformly from
      the positive events' observed year range; its MONTH is drawn from
      the empirical month distribution of the 2,242 dated positives
      (so negatives share the same seasonal/monsoon skew as positives,
      per the approved design); its DAY is drawn uniformly within that
      calendar month (leap years handled correctly).
    - Duplicate prevention: exact (rounded lat, rounded lon, date)
      triples are rejected against already-accepted negatives.
    - Reproducibility: single fixed seed (42) drives every random draw
      in this script, in a fixed order, so a rerun on the same inputs
      reproduces the same output file byte-for-byte.
    - Honesty on shortfall: if the 1 km exclusion rule makes the full
      requested count unreachable within the attempt budget, the
      script stops, reports exactly how many were generated and why,
      and does NOT silently shrink the exclusion radius or the study
      region to hit the target.

OUTPUT:
    data/gsi/gsi_pseudo_negative_samples.csv
        record_id, source, State, Latitude, Longitude, date, year,
        month, nearest_inventory_distance_km, landslide_event(=0)
"""

import calendar
from pathlib import Path

import numpy as np
import pandas as pd

# --------------------------------------------------------------------------
# CONFIG (approved parameters)
# --------------------------------------------------------------------------
INVENTORY_PATH = Path("data/gsi/gsi_landslide_inventory_normalized.csv")
DATED_EVENTS_PATH = Path("data/gsi/gsi_dated_events.csv")
OUTPUT_PATH = Path("data/gsi/gsi_pseudo_negative_samples.csv")

RANDOM_SEED = 42
EXCLUSION_RADIUS_KM = 1.0
NEG_POS_RATIO = 2.0

NER_STATES = [
    "Assam", "Arunachal Pradesh", "Manipur", "Meghalaya",
    "Mizoram", "Nagaland", "Sikkim", "Tripura",
]

# Padding added around each state's OBSERVED GSI point bounding box to
# define its sampling region. Documented approximation - see docstring.
NER_BBOX_PADDING_DEG = 0.15

# Coarse spatial hash cell size for fast exclusion-distance lookups.
# ~0.02 deg is a safe multiple of the 1 km exclusion radius at these
# latitudes (checking the 3x3 neighborhood around a candidate's cell
# covers well over 1 km in every direction).
GRID_CELL_DEG = 0.02

# Stratification grid inside each state's bounding box.
SUBCELLS_PER_STATE_SIDE = 8  # up to 8x8 = 64 sub-cells per state

# Attempt budget (per remaining unit of quota) before giving up on a
# state/cell rather than looping forever if the exclusion rule makes a
# region infeasible.
MAX_ATTEMPTS_PER_UNIT = 800
GLOBAL_MAX_ATTEMPTS = 2_000_000

COORD_ROUND_DECIMALS = 6  # ~0.11 m, used only for duplicate detection


# --------------------------------------------------------------------------
# GEOMETRY
# --------------------------------------------------------------------------
def haversine_km(lat1, lon1, lat2, lon2):
    """Vectorized great-circle distance (km). lat2/lon2 may be arrays."""
    R = 6371.0088
    lat1r = np.radians(lat1)
    lat2r = np.radians(lat2)
    dlat = np.radians(lat2 - lat1)
    dlon = np.radians(lon2 - lon1)
    a = np.sin(dlat / 2.0) ** 2 + np.cos(lat1r) * np.cos(lat2r) * np.sin(dlon / 2.0) ** 2
    a = np.clip(a, 0.0, 1.0)
    return 2 * R * np.arcsin(np.sqrt(a))


class ExclusionIndex:
    """
    Coarse grid spatial hash over the complete GSI inventory, used to find
    the nearest inventory point(s) to a candidate quickly instead of
    comparing against all 35,716 points every time.
    """

    def __init__(self, lats, lons, cell_deg):
        self.lats = np.asarray(lats, dtype=float)
        self.lons = np.asarray(lons, dtype=float)
        self.cell_deg = cell_deg
        cell_lat = np.floor(self.lats / cell_deg).astype(int)
        cell_lon = np.floor(self.lons / cell_deg).astype(int)
        self.grid = {}
        for i in range(len(self.lats)):
            key = (cell_lat[i], cell_lon[i])
            self.grid.setdefault(key, []).append(i)

    def min_distance_km(self, lat, lon):
        """
        Nearest-neighbor distance via an expanding-ring grid search.
        Starts at the 3x3 neighborhood (covers well over 1 km, cheap for
        the common case) and widens the ring until at least one inventory
        point is found, then widens one further ring as a safety margin
        so a point just across a cell boundary isn't missed. This avoids
        ever reporting an inaccurate/infinite distance for candidates in
        sparse regions - it always resolves to the true nearest point.
        """
        clat = int(np.floor(lat / self.cell_deg))
        clon = int(np.floor(lon / self.cell_deg))

        k = 1
        idx = []
        while not idx and k <= 50:
            idx = []
            for dlat in range(-k, k + 1):
                for dlon in range(-k, k + 1):
                    key = (clat + dlat, clon + dlon)
                    if key in self.grid:
                        idx.extend(self.grid[key])
            k += 1

        if not idx:
            # No inventory point within ~50 grid cells (>1000 km) - only
            # possible if the inventory were empty. Report a large finite
            # sentinel rather than inf so downstream stats stay valid.
            return 9999.0

        # one extra ring of safety margin beyond where points were first found
        idx = []
        for dlat in range(-k, k + 1):
            for dlon in range(-k, k + 1):
                key = (clat + dlat, clon + dlon)
                if key in self.grid:
                    idx.extend(self.grid[key])

        d = haversine_km(lat, lon, self.lats[idx], self.lons[idx])
        return float(d.min())


# --------------------------------------------------------------------------
# LOAD REAL DATA
# --------------------------------------------------------------------------
def load_inventory():
    if not INVENTORY_PATH.exists():
        raise SystemExit(f"\nFATAL: input file not found: {INVENTORY_PATH}")
    df = pd.read_csv(INVENTORY_PATH)
    raw_count = len(df)
    df["Latitude"] = pd.to_numeric(df["Latitude"], errors="coerce")
    df["Longitude"] = pd.to_numeric(df["Longitude"], errors="coerce")
    missing_coord = int((df["Latitude"].isna() | df["Longitude"].isna()).sum())
    df = df.dropna(subset=["Latitude", "Longitude"]).copy()
    return df, raw_count, missing_coord


def load_dated_events():
    if not DATED_EVENTS_PATH.exists():
        raise SystemExit(f"\nFATAL: input file not found: {DATED_EVENTS_PATH}")
    df = pd.read_csv(DATED_EVENTS_PATH)
    df["event_date"] = pd.to_datetime(df["event_date"], errors="coerce")
    missing_date = int(df["event_date"].isna().sum())
    return df, missing_date


# --------------------------------------------------------------------------
# STATE STUDY REGIONS (derived from actual observed GSI points, not
# assumed/hardcoded political boundaries)
# --------------------------------------------------------------------------
def build_state_bboxes(inventory_df):
    """
    Builds each state's study-region bounding box from its OBSERVED GSI
    points, using the 1st/99th percentile of lat/lon rather than raw
    min/max. This is a deliberate outlier guard: the source inventory
    is known to contain at least one physically implausible coordinate
    (see the printed WARNING below) that passed the -90/90 range check
    upstream in clean_gsi_inventory.py but is inconsistent with every
    other point recorded for that state. Using percentile bounds instead
    of min/max prevents one bad row from silently blowing up the entire
    sampling region; the source CSV itself is never modified, and every
    row flagged this way is printed for the user to verify against GSI.
    """
    bboxes = {}
    outlier_report = []
    for state in NER_STATES:
        sub = inventory_df[inventory_df["State"] == state]
        if len(sub) == 0:
            continue

        lat_p1, lat_p99 = np.percentile(sub["Latitude"], [1, 99])
        lon_p1, lon_p99 = np.percentile(sub["Longitude"], [1, 99])
        lat_min = lat_p1 - NER_BBOX_PADDING_DEG
        lat_max = lat_p99 + NER_BBOX_PADDING_DEG
        lon_min = lon_p1 - NER_BBOX_PADDING_DEG
        lon_max = lon_p99 + NER_BBOX_PADDING_DEG
        bboxes[state] = (lat_min, lat_max, lon_min, lon_max, len(sub))

        # flag any point far outside the percentile-based region (informational
        # only - does not remove the point from the exclusion mask, only from
        # the region used to decide WHERE to draw candidates)
        raw_lat_min, raw_lat_max = sub["Latitude"].min(), sub["Latitude"].max()
        raw_lon_min, raw_lon_max = sub["Longitude"].min(), sub["Longitude"].max()
        if raw_lat_min < lat_min or raw_lat_max > lat_max or raw_lon_min < lon_min or raw_lon_max > lon_max:
            outliers = sub[
                (sub["Latitude"] < lat_min) | (sub["Latitude"] > lat_max)
                | (sub["Longitude"] < lon_min) | (sub["Longitude"] > lon_max)
            ]
            for _, row in outliers.iterrows():
                outlier_report.append(
                    f"    {state}: {row.get('Slide_No', '?')}  "
                    f"lat={row['Latitude']}, lon={row['Longitude']} "
                    f"(outside the state's 1st-99th percentile region - "
                    f"excluded from region bounds, still active in the exclusion mask)"
                )

    if outlier_report:
        print("\nWARNING - coordinate outliers detected in the source inventory "
              "(not modified, excluded only from study-region bounds):")
        for line in outlier_report:
            print(line)

    return bboxes


# --------------------------------------------------------------------------
# DATE SAMPLING (from the real positive-event distribution)
# --------------------------------------------------------------------------
def build_month_distribution(dated_df):
    counts = dated_df["event_month"].value_counts().sort_index()
    months = counts.index.to_numpy()
    probs = (counts / counts.sum()).to_numpy()
    return months, probs


def sample_date(rng, year_min, year_max, months, month_probs):
    year = int(rng.integers(year_min, year_max + 1))
    month = int(rng.choice(months, p=month_probs))
    days_in_month = calendar.monthrange(year, month)[1]
    day = int(rng.integers(1, days_in_month + 1))
    return pd.Timestamp(year=year, month=month, day=day)


# --------------------------------------------------------------------------
# MAIN SAMPLING LOOP
# --------------------------------------------------------------------------
def main():
    rng = np.random.default_rng(RANDOM_SEED)

    inventory_df, inv_raw_count, missing_coord_count = load_inventory()
    dated_df, missing_date_count = load_dated_events()

    n_positive = len(dated_df)
    target_negatives = int(round(NEG_POS_RATIO * n_positive))

    print("=" * 70)
    print("PSEUDO-NEGATIVE / BACKGROUND SAMPLE GENERATION")
    print("=" * 70)
    print(f"Loaded inventory:      {INVENTORY_PATH} ({inv_raw_count:,} rows read, "
          f"{missing_coord_count:,} missing/invalid coordinates, "
          f"{len(inventory_df):,} usable for exclusion mask)")
    print(f"Loaded dated events:   {DATED_EVENTS_PATH} ({n_positive:,} positive events, "
          f"{missing_date_count:,} missing event_date)")
    print(f"Positive count:        {n_positive:,}")
    print(f"Target ratio:          {NEG_POS_RATIO}:1")
    print(f"Requested negatives:   {target_negatives:,}")
    print(f"Random seed:           {RANDOM_SEED}")
    print(f"Exclusion radius:      {EXCLUSION_RADIUS_KM} km (against COMPLETE GSI "
          f"inventory - dated + year-only + undated)")

    year_min = int(dated_df["event_year"].min())
    year_max = int(dated_df["event_year"].max())
    months, month_probs = build_month_distribution(dated_df)
    print(f"\nPositive event year range: {year_min}-{year_max}")
    print("Positive event month distribution (used to date negatives):")
    for m, p in zip(months, month_probs):
        print(f"    month {int(m):>2}: {p*100:5.1f}%")

    state_bboxes = build_state_bboxes(inventory_df)
    print(f"\nNER states with usable GSI points: {len(state_bboxes)}/{len(NER_STATES)}")
    missing_states = [s for s in NER_STATES if s not in state_bboxes]
    if missing_states:
        print(f"  WARNING - no inventory points found for: {missing_states} "
              f"(no study region could be built for these states)")

    exclusion_index = ExclusionIndex(
        inventory_df["Latitude"].to_numpy(),
        inventory_df["Longitude"].to_numpy(),
        GRID_CELL_DEG,
    )

    # ---- quota split ~evenly across the states we actually have a region for ----
    present_states = sorted(state_bboxes.keys())
    n_states = len(present_states)
    base_quota = target_negatives // n_states
    remainder = target_negatives - base_quota * n_states
    quotas = {s: base_quota for s in present_states}
    for i, s in enumerate(present_states):
        if i < remainder:
            quotas[s] += 1

    print("\nPer-state negative quota (even split across states with a study region):")
    for s in present_states:
        print(f"    {s:<20} quota={quotas[s]:>5}  "
              f"study-region lat[{state_bboxes[s][0]:.3f},{state_bboxes[s][1]:.3f}] "
              f"lon[{state_bboxes[s][2]:.3f},{state_bboxes[s][3]:.3f}] "
              f"(from {state_bboxes[s][4]} GSI points)")

    # ---- generate ----
    accepted_rows = []
    seen_keys = set()
    duplicate_rejections = 0
    exclusion_rejections = 0
    total_attempts = 0
    shortfall_states = {}
    record_counter = 1

    for state in present_states:
        lat_min, lat_max, lon_min, lon_max, _ = state_bboxes[state]
        quota = quotas[state]
        if quota == 0:
            continue

        # stratification sub-grid within this state's bounding box
        n_side = min(SUBCELLS_PER_STATE_SIDE, max(1, int(np.ceil(np.sqrt(quota)))))
        lat_edges = np.linspace(lat_min, lat_max, n_side + 1)
        lon_edges = np.linspace(lon_min, lon_max, n_side + 1)
        cells = [
            (lat_edges[i], lat_edges[i + 1], lon_edges[j], lon_edges[j + 1])
            for i in range(n_side)
            for j in range(n_side)
        ]

        accepted_for_state = 0
        cell_ptr = 0
        attempts_this_state = 0
        max_attempts_this_state = MAX_ATTEMPTS_PER_UNIT * max(quota, 1)

        while accepted_for_state < quota and attempts_this_state < max_attempts_this_state:
            if total_attempts >= GLOBAL_MAX_ATTEMPTS:
                break

            cell = cells[cell_ptr % len(cells)]
            cell_ptr += 1
            c_lat_min, c_lat_max, c_lon_min, c_lon_max = cell

            candidate_lat = rng.uniform(c_lat_min, c_lat_max)
            candidate_lon = rng.uniform(c_lon_min, c_lon_max)

            attempts_this_state += 1
            total_attempts += 1

            dist_km = exclusion_index.min_distance_km(candidate_lat, candidate_lon)
            if dist_km < EXCLUSION_RADIUS_KM:
                exclusion_rejections += 1
                continue

            candidate_date = sample_date(rng, year_min, year_max, months, month_probs)
            date_str = candidate_date.strftime("%Y-%m-%d")

            key = (
                round(candidate_lat, COORD_ROUND_DECIMALS),
                round(candidate_lon, COORD_ROUND_DECIMALS),
                date_str,
            )
            if key in seen_keys:
                duplicate_rejections += 1
                continue
            seen_keys.add(key)

            accepted_rows.append({
                "record_id": f"NEG_{record_counter:06d}",
                "source": "pseudo_negative",
                "State": state,
                "Latitude": round(candidate_lat, 6),
                "Longitude": round(candidate_lon, 6),
                "date": date_str,
                "year": candidate_date.year,
                "month": candidate_date.month,
                "nearest_inventory_distance_km": round(dist_km, 4),
                "landslide_event": 0,
            })
            record_counter += 1
            accepted_for_state += 1

        if accepted_for_state < quota:
            shortfall_states[state] = (accepted_for_state, quota)

        print(f"  [{state}] accepted {accepted_for_state}/{quota} "
              f"(attempts={attempts_this_state}, "
              f"exclusion-rejected so far in run={exclusion_rejections}, "
              f"duplicate-rejected so far in run={duplicate_rejections})")

        if total_attempts >= GLOBAL_MAX_ATTEMPTS:
            print("  GLOBAL ATTEMPT BUDGET REACHED - stopping generation cleanly.")
            break

    out_df = pd.DataFrame(accepted_rows)

    # ---- save ----
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    out_df.to_csv(OUTPUT_PATH, index=False)

    # ------------------------------------------------------------------
    # VALIDATION REPORT
    # ------------------------------------------------------------------
    print("\n" + "=" * 70)
    print("VALIDATION REPORT")
    print("=" * 70)
    print(f"Number of positive events:        {n_positive:,}")
    print(f"Requested negative count:         {target_negatives:,}")
    print(f"Generated negative count:         {len(out_df):,}")
    achieved_ratio = len(out_df) / n_positive if n_positive else float("nan")
    print(f"Actual negative:positive ratio:   {achieved_ratio:.3f} : 1")

    print("\nStates/regions represented:")
    if len(out_df):
        print(out_df["State"].value_counts().reindex(present_states).fillna(0).astype(int).to_string())
    else:
        print("  (none generated)")

    print("\nNegative date/month distribution:")
    if len(out_df):
        print(out_df["month"].value_counts().sort_index().to_string())
        print(f"  Year range sampled: {out_df['year'].min()}-{out_df['year'].max()}")
    else:
        print("  (none generated)")

    if len(out_df):
        print(f"\nMinimum distance to any GSI inventory point achieved: "
              f"{out_df['nearest_inventory_distance_km'].min():.4f} km "
              f"(exclusion floor was {EXCLUSION_RADIUS_KM} km)")
        print(f"Mean distance to nearest GSI inventory point: "
              f"{out_df['nearest_inventory_distance_km'].mean():.4f} km")

    print(f"\nDuplicate candidates rejected during generation: {duplicate_rejections:,}")
    print(f"Exclusion-zone candidates rejected during generation: {exclusion_rejections:,}")
    print(f"Total candidate attempts: {total_attempts:,}")
    print(f"Missing coordinate count (inventory, excluded from exclusion mask): {missing_coord_count:,}")
    print(f"Missing date count (positive events): {missing_date_count:,}")
    print(f"Random seed used: {RANDOM_SEED}")

    if shortfall_states:
        print("\n" + "!" * 70)
        print("SHORTFALL - the 1 km exclusion rule was NOT weakened to compensate.")
        print("The following states did not reach their requested quota:")
        for s, (got, want) in shortfall_states.items():
            print(f"    {s}: generated {got} of {want} requested")
        total_short = sum(want - got for got, want in shortfall_states.values())
        print(f"Total shortfall vs. requested {target_negatives:,}: {total_short:,} "
              f"({len(out_df):,} actually generated)")
        print("!" * 70)
    else:
        print("\nAll state quotas reached in full - no shortfall.")

    print(f"\nSaved: {OUTPUT_PATH}")
    print("\nREMINDER: every row in this file is source='pseudo_negative' - a location")
    print("GSI has not documented a landslide at, NOT a confirmed safe/no-landslide")
    print("observation. This distinction must be preserved in every downstream use.")
    print("=" * 70)


if __name__ == "__main__":
    main()
