import re
from pathlib import Path

import pandas as pd


RAW_PATH = Path("data/gsi/gsi_raw_extracted.csv")
OUTPUT_PATH = Path("data/gsi/gsi_landslide_inventory.csv")


EXPECTED_COLUMNS = [
    "Sl.No.",
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
]


def clean_text(value):
    """Normalize a cell to a clean string."""
    if pd.isna(value):
        return ""
    text = str(value).replace("\n", " ").replace("\r", " ")
    text = re.sub(r"\s+", " ", text).strip()
    return text


def parse_history_date(value):
    """
    Parse full dates such as:
      17 May 2016
      18 May 2016
      02 June 2020

    Returns NaT when the field is NA, a year-only value,
    or otherwise not a full date.
    """
    text = clean_text(value)

    if not text or text.upper() in {"NA", "N/A", "-", "--"}:
        return pd.NaT

    for fmt in ("%d %B %Y", "%d %b %Y"):
        parsed = pd.to_datetime(text, format=fmt, errors="coerce")
        if not pd.isna(parsed):
            return parsed

    return pd.NaT


def extract_year(value):
    """
    Extract a four-digit year from History when available.
    """
    text = clean_text(value)

    if not text or text.upper() in {"NA", "N/A", "-", "--"}:
        return pd.NA

    match = re.search(r"\b(19|20)\d{2}\b", text)
    if match:
        return int(match.group(0))

    return pd.NA


print("=" * 70)
print("GSI FIELD-VALIDATED LANDSLIDE INVENTORY CLEANING")
print("=" * 70)

if not RAW_PATH.exists():
    raise FileNotFoundError(f"Raw file not found: {RAW_PATH}")

print(f"\nLoading: {RAW_PATH}")

raw = pd.read_csv(
    RAW_PATH,
    header=None,
    dtype=str,
    keep_default_na=False,
)

print(f"Raw shape: {raw.shape}")

# ---------------------------------------------------------------------
# 1. Find the real table header
# ---------------------------------------------------------------------

header_index = None

for idx in range(len(raw)):
    row = [clean_text(x) for x in raw.iloc[idx].tolist()]
    joined = " | ".join(row).lower()

    if "sl.no." in joined and "slide_no" in joined and "latitude" in joined:
        header_index = idx
        break

if header_index is None:
    raise RuntimeError(
        "Could not identify the GSI inventory header row."
    )

print(f"Header row found at raw row: {header_index}")

# ---------------------------------------------------------------------
# 2. Extract rows after the header
# ---------------------------------------------------------------------

data = raw.iloc[header_index + 1:].copy()

# The PDF extraction has the same 11-field table throughout.
if data.shape[1] < len(EXPECTED_COLUMNS):
    raise RuntimeError(
        f"Expected at least {len(EXPECTED_COLUMNS)} columns, "
        f"but found {data.shape[1]}."
    )

# Keep only the first 11 inventory columns.
data = data.iloc[:, :len(EXPECTED_COLUMNS)].copy()
data.columns = EXPECTED_COLUMNS

# Clean every cell
for col in data.columns:
    data[col] = data[col].map(clean_text)

# ---------------------------------------------------------------------
# 3. Remove repeated page headers / obvious non-data rows
# ---------------------------------------------------------------------

# Remove repeated header rows
header_mask = (
    data["Slide_No"].str.lower().eq("slide_no")
    | data["State"].str.lower().eq("state")
)

repeated_headers = int(header_mask.sum())
data = data.loc[~header_mask].copy()

# Keep rows having something that looks like a Slide_No.
# This removes title/footnote/page fragments without inventing data.
before_slide_filter = len(data)

slide_no_mask = data["Slide_No"].str.len() > 0
data = data.loc[slide_no_mask].copy()

removed_without_slide_no = before_slide_filter - len(data)

# ---------------------------------------------------------------------
# 4. Numeric coordinate validation
# ---------------------------------------------------------------------

data["Latitude"] = pd.to_numeric(data["Latitude"], errors="coerce")
data["Longitude"] = pd.to_numeric(data["Longitude"], errors="coerce")

valid_coord_mask = (
    data["Latitude"].between(-90, 90)
    & data["Longitude"].between(-180, 180)
)

invalid_coordinate_rows = int((~valid_coord_mask).sum())

data = data.loc[valid_coord_mask].copy()

# ---------------------------------------------------------------------
# 5. Normalize categorical/text fields
# ---------------------------------------------------------------------

text_columns = [
    "Slide_No",
    "State",
    "District",
    "Slide_Name",
    "NH_SH_Location",
    "Material_Involved",
    "Movement_Type",
    "History",
]

for col in text_columns:
    data[col] = data[col].map(clean_text)

# Normalize State to title case while preserving common state names
data["State"] = (
    data["State"]
    .str.strip()
    .str.replace(r"\s+", " ", regex=True)
)

data["District"] = (
    data["District"]
    .str.strip()
    .str.replace(r"\s+", " ", regex=True)
)

# ---------------------------------------------------------------------
# 6. Parse history/date information
# ---------------------------------------------------------------------

data["Occurrence_Date"] = data["History"].map(parse_history_date)

data["Occurrence_Year"] = data["History"].map(extract_year)

# ---------------------------------------------------------------------
# 7. Remove duplicate inventory records
# ---------------------------------------------------------------------

before_dedup = len(data)

# Slide_No is the strongest available identifier.
# Fall back to coordinates/state/district/name only when Slide_No is blank.
data["_dedup_key"] = data["Slide_No"]

fallback_mask = data["_dedup_key"].eq("")

data.loc[fallback_mask, "_dedup_key"] = (
    data.loc[fallback_mask, "State"].str.upper()
    + "|"
    + data.loc[fallback_mask, "District"].str.upper()
    + "|"
    + data.loc[fallback_mask, "Latitude"].round(6).astype(str)
    + "|"
    + data.loc[fallback_mask, "Longitude"].round(6).astype(str)
    + "|"
    + data.loc[fallback_mask, "Slide_Name"].str.upper()
)

data = data.drop_duplicates(subset="_dedup_key", keep="first")

duplicates_removed = before_dedup - len(data)

data = data.drop(columns=["_dedup_key"])

# ---------------------------------------------------------------------
# 8. Final column ordering
# ---------------------------------------------------------------------

final_columns = EXPECTED_COLUMNS + [
    "Occurrence_Date",
    "Occurrence_Year",
]

data = data[final_columns].copy()

# Sort for easier inspection
data = data.sort_values(
    by=["State", "District", "Occurrence_Year", "Slide_No"],
    na_position="last",
).reset_index(drop=True)

# ---------------------------------------------------------------------
# 9. Save
# ---------------------------------------------------------------------

OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)

data.to_csv(
    OUTPUT_PATH,
    index=False,
    encoding="utf-8-sig",
)

# ---------------------------------------------------------------------
# 10. Report
# ---------------------------------------------------------------------

print("\n" + "=" * 70)
print("CLEANING COMPLETE")
print("=" * 70)

print(f"Raw rows:                         {len(raw):,}")
print(f"Repeated header rows removed:     {repeated_headers:,}")
print(f"Rows without Slide_No removed:    {removed_without_slide_no:,}")
print(f"Invalid coordinate rows removed:  {invalid_coordinate_rows:,}")
print(f"Duplicate records removed:        {duplicates_removed:,}")
print(f"Final usable records:             {len(data):,}")

print(
    f"\nRecords with full occurrence date: "
    f"{data['Occurrence_Date'].notna().sum():,}"
)

print(
    f"Records with occurrence year: "
    f"{data['Occurrence_Year'].notna().sum():,}"
)

print(
    f"Records missing occurrence date: "
    f"{data['Occurrence_Date'].isna().sum():,}"
)

print(f"\nStates represented: {data['State'].nunique(dropna=True)}")
print("\nState counts:")
print(data["State"].value_counts().to_string())

print("\nSample cleaned records:")
print(data.head(10).to_string(index=False))

print(f"\nSaved to:")
print(OUTPUT_PATH)
print("=" * 70)