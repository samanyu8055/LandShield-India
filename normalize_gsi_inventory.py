from pathlib import Path
import pandas as pd

INPUT = Path("data/gsi/gsi_landslide_inventory.csv")
OUTPUT = Path("data/gsi/gsi_landslide_inventory_normalized.csv")

print("=" * 70)
print("NORMALIZING GSI LANDSLIDE INVENTORY")
print("=" * 70)

df = pd.read_csv(INPUT, dtype=str)

print(f"Input rows: {len(df):,}")

# Normalize whitespace first
for col in df.columns:
    df[col] = df[col].fillna("").astype(str).str.strip()

# State-name normalization
STATE_MAP = {
    "KERALA": "Kerala",
    "KARNATAKA": "Karnataka",
    "MEGHALAYA": "Meghalaya",
    "Tamil nadu": "Tamil Nadu",
    "TAMIL NADU": "Tamil Nadu",
    "-Arunachal Pradesh": "Arunachal Pradesh",
    "Arunachal Pradesh": "Arunachal Pradesh",
    "UT: Ladakh": "Ladakh",
    "Jammu & Kashmir (UT)": "Jammu & Kashmir",
}

df["State"] = df["State"].replace(STATE_MAP)

# Normalize obvious whitespace/case variants
df["State"] = (
    df["State"]
    .str.replace(r"\s+", " ", regex=True)
    .str.strip()
)

# Convert coordinates
df["Latitude"] = pd.to_numeric(df["Latitude"], errors="coerce")
df["Longitude"] = pd.to_numeric(df["Longitude"], errors="coerce")

# Convert dates
df["Occurrence_Date"] = pd.to_datetime(
    df["Occurrence_Date"],
    errors="coerce"
)

df["Occurrence_Year"] = pd.to_numeric(
    df["Occurrence_Year"],
    errors="coerce"
).astype("Int64")

# Remove impossible coordinates
valid_coords = (
    df["Latitude"].between(-90, 90)
    & df["Longitude"].between(-180, 180)
)

before = len(df)
df = df.loc[valid_coords].copy()

print(f"Removed invalid coordinates: {before - len(df):,}")

# Remove duplicate Slide_No where available
before = len(df)

has_slide_no = df["Slide_No"].ne("")
df_with_id = df.loc[has_slide_no].drop_duplicates(
    subset=["Slide_No"],
    keep="first"
)

df_without_id = df.loc[~has_slide_no].copy()

df = pd.concat(
    [df_with_id, df_without_id],
    ignore_index=True
)

print(f"Additional duplicate Slide_No records removed: {before - len(df):,}")

# Sort
df = df.sort_values(
    ["State", "District", "Occurrence_Date", "Slide_No"],
    na_position="last"
).reset_index(drop=True)

# Save
OUTPUT.parent.mkdir(parents=True, exist_ok=True)

df.to_csv(
    OUTPUT,
    index=False,
    encoding="utf-8-sig"
)

print("\n" + "=" * 70)
print("NORMALIZATION COMPLETE")
print("=" * 70)

print(f"Final rows: {len(df):,}")
print(f"States/UTs: {df['State'].nunique()}")

print("\nNormalized state counts:")
print(df["State"].value_counts().to_string())

print("\nFully dated records:",
      df["Occurrence_Date"].notna().sum())

print("Records with occurrence year:",
      df["Occurrence_Year"].notna().sum())

print("\nSaved:")
print(OUTPUT)

print("=" * 70)