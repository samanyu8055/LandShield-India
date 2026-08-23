import pdfplumber
import pandas as pd
from pathlib import Path

PDF_PATH = Path("data/gsi/landslide_report.pdf")
OUTPUT_PATH = Path("data/gsi/gsi_field_validated.csv")

print("Starting GSI PDF extraction...")
print(f"PDF: {PDF_PATH}")

all_rows = []

with pdfplumber.open(PDF_PATH) as pdf:

    print(f"Total pages: {len(pdf.pages)}")

    for page_number, page in enumerate(pdf.pages, start=1):

        try:
            tables = page.extract_tables()

            for table in tables:

                if not table:
                    continue

                for row in table:

                    if row:
                        cleaned = [
                            str(cell).strip() if cell is not None else ""
                            for cell in row
                        ]

                        all_rows.append(cleaned)

            if page_number % 50 == 0:
                print(f"Processed {page_number} pages...")

        except Exception as e:
            print(f"Page {page_number} error: {e}")

print("Finished extracting PDF.")

# Remove completely empty rows
all_rows = [
    row for row in all_rows
    if any(str(cell).strip() for cell in row)
]

print(f"Rows extracted: {len(all_rows)}")

# Save raw extraction first
raw_path = Path("data/gsi/gsi_raw_extracted.csv")

pd.DataFrame(all_rows).to_csv(
    raw_path,
    index=False,
    header=False
)

print(f"Raw data saved to: {raw_path}")

print("Done.")