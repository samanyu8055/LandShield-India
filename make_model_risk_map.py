"""
make_model_risk_map.py

SIH26001 LandslideShield -- V1 model risk map

Loads the already-trained V1 model and scores the cleaned GSI
model-training points (NOT a full India-wide grid -- just the points
that were used to train/test the model). Renders an interactive Folium
map colored by susceptibility band.

INPUT
-----
models/landslide_xgb.pkl
data/gsi/gsi_model_training.csv

OUTPUT
------
maps/landslide_v1_risk_map.html

This does NOT train, retrain, or modify the model or any existing file.
This is a visualization of scores on known sample points, not a
prediction grid covering all of India.
"""

from pathlib import Path
import pickle
import sys

import numpy as np
import pandas as pd

try:
    import folium
except ImportError:
    print("ERROR: folium is not installed in this environment.")
    print("Install it with:\n\n    pip install folium\n")
    sys.exit(1)

MODEL_FILE = Path("models/landslide_xgb.pkl")
DATA_FILE = Path("data/gsi/gsi_model_training.csv")
OUTPUT_FILE = Path("maps/landslide_v1_risk_map.html")

FEATURES = [
    "elevation_m",
    "slope_deg",
    "historical_landslide_density",
    "historical_landslide_distance",
]

# (max_score_exclusive, label, color)
RISK_BANDS = [
    (25, "LOW", "green"),
    (50, "MODERATE", "gold"),
    (75, "HIGH", "orange"),
    (101, "VERY HIGH", "red"),
]


def risk_band(score: float):
    for upper, label, color in RISK_BANDS:
        if score < upper:
            return label, color
    return "VERY HIGH", "red"


def log(msg):
    print(msg, flush=True)


def main():
    if not MODEL_FILE.exists():
        log(f"FATAL: {MODEL_FILE} not found. Train the V1 model first.")
        sys.exit(1)
    if not DATA_FILE.exists():
        log(f"FATAL: {DATA_FILE} not found. Run train_landslide_model.py first.")
        sys.exit(1)

    log(f"Loading model -> {MODEL_FILE}")
    with open(MODEL_FILE, "rb") as f:
        model = pickle.load(f)

    log(f"Loading points -> {DATA_FILE}")
    df = pd.read_csv(DATA_FILE)
    df = df.dropna(subset=FEATURES).reset_index(drop=True)
    log(f"Scoring {len(df)} points")

    proba = model.predict_proba(df[FEATURES])[:, 1]
    df["risk_score"] = np.round(proba * 100, 1)
    bands = df["risk_score"].apply(risk_band)
    df["risk_label"] = bands.apply(lambda x: x[0])
    df["risk_color"] = bands.apply(lambda x: x[1])

    log("Risk band counts:")
    log(df["risk_label"].value_counts().to_string())

    # Center/fit to the actual data extent instead of hard-coding a region.
    min_lat, max_lat = df["latitude"].min(), df["latitude"].max()
    min_lon, max_lon = df["longitude"].min(), df["longitude"].max()
    center_lat = (min_lat + max_lat) / 2
    center_lon = (min_lon + max_lon) / 2

    fmap = folium.Map(location=[center_lat, center_lon], zoom_start=5, tiles="OpenStreetMap")
    fmap.fit_bounds([[min_lat, min_lon], [max_lat, max_lon]])

    fmap.get_root().html.add_child(folium.Element(
        "<div style='position:fixed;top:10px;left:60px;z-index:9999;"
        "background:white;padding:8px 12px;border:1px solid #999;"
        "border-radius:4px;font-size:13px;max-width:340px;'>"
        "<b>LandslideShield V1 -- model risk map</b><br>"
        "Susceptibility scores on the cleaned GSI training/test points "
        "used to build the V1 model. This is <b>not</b> an India-wide "
        "prediction grid.</div>"
    ))

    groups = {label: folium.FeatureGroup(name=f"{label} ({color})")
              for _, label, color in RISK_BANDS}
    for group in groups.values():
        group.add_to(fmap)

    for row in df.itertuples():
        popup_html = (
            f"<b>State:</b> {row.State}<br>"
            f"<b>Lat/Lon:</b> {row.latitude:.5f}, {row.longitude:.5f}<br>"
            f"<b>Risk score:</b> {row.risk_score:.1f} ({row.risk_label})<br>"
            f"<b>Landslide label:</b> {row.landslide_event}<br>"
            f"<b>Elevation:</b> {row.elevation_m:.1f} m<br>"
            f"<b>Slope:</b> {row.slope_deg:.2f} deg<br>"
            f"<b>Historical density:</b> {row.historical_landslide_density}<br>"
            f"<b>Historical distance:</b> {row.historical_landslide_distance:.3f} km"
        )
        folium.CircleMarker(
            location=[row.latitude, row.longitude],
            radius=4,
            color=row.risk_color,
            fill=True,
            fill_color=row.risk_color,
            fill_opacity=0.75,
            weight=1,
            popup=folium.Popup(popup_html, max_width=280),
        ).add_to(groups[row.risk_label])

    folium.LayerControl(collapsed=False).add_to(fmap)

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    fmap.save(str(OUTPUT_FILE))
    log(f"\nSaved map -> {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
