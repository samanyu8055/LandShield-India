from pathlib import Path
import pandas as pd

INPUT = Path("data/gsi/gsi_landslide_inventory_normalized.csv")

DATED_OUTPUT = Path("data/gsi/gsi_dated_events.csv")
YEAR_ONLY_OUTPUT = Path("data/gsi/gsi_year_only_inventory.csv")

print("=" * 70)
print("PREPARING GSI LANDSLIDE DATA FOR MODELING")
print("=" * 70)

df = pd.read_csv(INPUT, dtype=str)

print(f"\nInput records: {len(df):,}")

# Convert fields properly
df["Latitude"] = pd.to_numeric(df["Latitude"], errors="coerce")
df["Longitude"] = pd.to_numeric(df["Longitude"], errors="coerce")

df["Occurrence_Date"] = pd.to_datetime(
    df["Occurrence_Date"],
    errors="coerce"
)

df["Occurrence_Year"] = pd.to_numeric(
    df["Occurrence_Year"],
    errors="coerce"
)

# Valid geographic coordinates
valid_coords = (
    df["Latitude"].between(-90, 90)
    & df["Longitude"].between(-180, 180)
)

df = df.loc[valid_coords].copy()

# ------------------------------------------------------------------
# DATED EVENTS
# ------------------------------------------------------------------

dated = df.loc[df["Occurrence_Date"].notna()].copy()

dated = dated.sort_values(
    ["Occurrence_Date", "State", "District", "Slide_No"]
).reset_index(drop=True)

# Useful explicit target column
dated["landslide_event"] = 1

# Date-derived fields
dated["event_date"] = dated["Occurrence_Date"].dt.strftime("%Y-%m-%d")
dated["event_year"] = dated["Occurrence_Date"].dt.year
dated["event_month"] = dated["Occurrence_Date"].dt.month

# Keep useful fields
dated_columns = [
    "Slide_No",
    "State",
    "District",
    "Slide_Name",
    "NH_SH_Location",
    "Latitude",
    "Longitude",
    "Material_Involved",
    "Movement_Type",
    "History",
    "Occurrence_Date",
    "Occurrence_Year",
    "event_date",
    "event_year",
    "event_month",
    "landslide_event",
]

dated = dated[dated_columns].copy()

# ------------------------------------------------------------------
# YEAR-ONLY HISTORICAL INVENTORY
# ------------------------------------------------------------------

year_only = df.loc[
    df["Occurrence_Date"].isna()
    & df["Occurrence_Year"].notna()
].copy()

year_only = year_only.sort_values(
    ["Occurrence_Year", "State", "District", "Slide_No"],
    na_position="last"
).reset_index(drop=True)

year_only["landslide_event"] = 1

# ------------------------------------------------------------------
# SAVE
# ------------------------------------------------------------------

DATED_OUTPUT.parent.mkdir(parents=True, exist_ok=True)

dated.to_csv(
    DATED_OUTPUT,
    index=False,
    encoding="utf-8-sig"
)

year_only.to_csv(
    YEAR_ONLY_OUTPUT,
    index=False,
    encoding="utf-8-sig"
)

# ------------------------------------------------------------------
# REPORT
# ------------------------------------------------------------------

print("\n" + "=" * 70)
print("PREPARATION COMPLETE")
print("=" * 70)

print(f"All normalized records:              {len(df):,}")
print(f"Fully dated landslide events:        {len(dated):,}")
print(f"Year-only historical records:        {len(year_only):,}")

print("\nDated event year range:")

if len(dated) > 0:
    print(
        f"{dated['event_year'].min()} "
        f"to "
        f"{dated['event_year'].max()}"
    )

print("\nDated events by state:")
print(
    dated["State"]
    .value_counts()
    .to_string()
)

print("\nDated events by year:")
print(
    dated["event_year"]
    .value_counts()
    .sort_index()
    .to_string()
)

print("\nSaved files:")
print(DATED_OUTPUT)
print(YEAR_ONLY_OUTPUT)

print("=" * 70)