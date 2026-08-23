# 🛰️ LandShield India

## AI-Powered Landslide Risk Monitoring & Response Platform for Northeast India

**Smart India Hackathon 2026 — SIH26001**  
**Category:** Disaster Management  

---

## 🌏 Overview

**LandShield India** is an AI-powered geospatial decision-support platform designed to assess, visualize and monitor landslide risk across the **Northeastern Region (NER) of India**.

The platform combines multiple geospatial and environmental information layers, including:

- 🌧️ Rainfall and environmental conditions
- ⛰️ Elevation and terrain characteristics
- 📐 Slope
- 🛰️ NDVI / vegetation information
- 📍 Historical landslide locations
- 🗺️ Historical landslide susceptibility
- 🛣️ Roads and infrastructure
- 🏘️ Settlements and critical facilities
- 👥 Field and citizen observations

These inputs are processed into a machine-learning-based risk assessment and visualized through GIS maps.

The core objective is not simply to identify landslide-prone areas, but to connect:

> **Risk → Explanation → Impact → Priority → Action**

---

# 🎯 Problem Statement

The **Northeastern Region of India** contains extensive mountainous and hilly terrain with steep slopes and areas susceptible to landslides.

Landslide information can originate from many different sources, such as:

- Rainfall and environmental conditions
- Terrain and elevation
- Slope
- Vegetation
- Historical landslide inventories
- GIS datasets
- Roads and infrastructure
- Settlements and critical facilities
- Field observations

The challenge is not only to identify areas that may be susceptible to landslides, but also to combine these different information layers into an understandable and actionable decision-support system.

Authorities and disaster-management teams need to answer questions such as:

> **Where is the risk highest?**

> **Why is the risk high?**

> **What could be affected?**

> **Where should response efforts be prioritized?**

LandShield India is designed around these questions.

---

# 💡 Our Solution

LandShield India creates an integrated geospatial workflow that combines environmental data, terrain information, historical landslide evidence and machine learning.

The platform follows the workflow:

```text
Data Sources
     ↓
Data Preparation & Cleaning
     ↓
Feature Engineering
     ↓
Machine Learning Model
     ↓
Risk Assessment
     ↓
Explainable AI (SHAP)
     ↓
GIS Risk Visualization
     ↓
Impact Assessment
     ↓
Response Prioritization
     ↓
Decision Support
````

The broader approach is:

> **Predict → Verify → Assess Impact → Prioritize → Alert**

---

# 🧩 Key Features

## 1. 🧠 AI-Based Risk Assessment

LandShield India uses machine-learning models to analyze multiple environmental and geospatial features and generate a landslide-risk indicator.

The repository supports machine-learning workflows using:

* **XGBoost**
* **Random Forest**
* **Scikit-learn**

The exact model and feature set can be configured according to data availability and validation results.

---

## 2. 🌧️ Environmental & Terrain Analysis

The system can combine environmental and terrain variables such as:

| Feature                                | Purpose                                            |
| -------------------------------------- | -------------------------------------------------- |
| 🌧️ Rainfall / Environmental Variables | Represent changing environmental conditions        |
| ⛰️ Elevation                           | Represent terrain characteristics                  |
| 📐 Slope                               | Identify steep terrain                             |
| 🌿 NDVI                                | Represent vegetation condition                     |
| 📍 Historical Landslides               | Provide historical spatial evidence                |
| 🗺️ Historical Susceptibility          | Represent long-term spatial risk                   |
| 💧 Environmental Indicators            | Represent changing ground/environmental conditions |

These features are transformed into model-ready data through the project's geospatial preprocessing pipeline.

---

# 📊 Risk Score

The model produces a **risk score** that can be represented on a 0–100 scale for visualization and decision support.

A prototype classification can use:

|  Score | Risk Level   |
| -----: | ------------ |
|   0–20 | 🟢 LOW       |
|  21–40 | 🟡 MODERATE  |
|  41–60 | 🟠 ELEVATED  |
|  61–80 | 🔴 HIGH      |
| 81–100 | 🚨 VERY HIGH |

> **Important:** These thresholds are configurable prototype thresholds. They should be calibrated and validated using appropriate independent data before operational deployment.

The current risk score should be interpreted as a **prototype decision-support indicator**, not as a scientifically validated probability that a landslide will occur.

---

# 🔍 Explainable AI

A major component of LandShield India is **explainability**.

Instead of showing only:

```text
Risk Score: 82 / 100
Risk Level: VERY HIGH
```

the system can identify important contributing factors.

For example:

```text
Risk Score: 82 / 100

Risk Level: VERY HIGH

Important contributing factors:
- High slope
- Historical landslide susceptibility
- Environmental conditions
- Vegetation indicator
```

The project uses **SHAP (SHapley Additive exPlanations)** to help interpret model predictions.

This makes the system easier to:

* Understand
* Audit
* Compare
* Debug
* Communicate to decision-makers

The objective is to answer:

> **Why did the model assign this area a high-risk score?**

---

# 🗺️ GIS-Based Risk Mapping

LandShield India converts model outputs into spatially understandable GIS risk maps.

The GIS component can be used to:

* Identify high-risk regions
* Visualize spatial risk patterns
* Display historical landslide locations
* Compare risk across locations
* Support infrastructure impact assessment
* Provide a visual interface for disaster-management teams

The repository includes generated GIS/map outputs under the `maps/` directory.

---

# 🚨 From Risk to Response Priority

A key difference in the LandShield India approach is that the system does not stop at:

> **"This location has high landslide risk."**

It also attempts to determine:

> **"What could be affected if a landslide occurs here?"**

Potential impact layers can include:

* 🛣️ Roads
* 🏘️ Villages / settlements
* 🏥 Hospitals
* 🏫 Schools
* ⚡ Critical infrastructure
* 🚧 Important transport routes

This allows a risk map to become a **response-prioritization tool**.

---

## Example

```text
AREA A

Landslide Risk:     82 / 100
Risk Level:         VERY HIGH

Potential Impact:
- 2 roads
- 3 settlements
- 1 critical facility

Response Priority: #1
```

The purpose is to help decision-makers distinguish between:

```text
High Risk + Low Impact
```

and

```text
High Risk + High Impact
```

so that limited response resources can be prioritized more effectively.

---

# 👥 Human-in-the-Loop Verification

Environmental data and AI predictions should not be treated as the only source of truth.

LandShield India is designed around a **human-in-the-loop** approach where field officers and citizens can contribute observations.

Possible observations include:

* Visible ground cracks
* Slope movement
* Road blockage
* New landslide occurrence
* Drainage problems
* Suspected ground deformation
* Photographic evidence

### Verification Workflow

```text
Citizen / Field Report
        ↓
Geo-tagged Observation
        ↓
LandShield India Platform
        ↓
Admin / Authority Review
        ↓
Verified Observation
        ↓
Decision Support
```

This approach allows local observations to complement satellite, environmental and historical datasets.

---

# 🧠 Why Human Verification Matters

AI models operate on available data.

Real-world conditions can change quickly, and some important observations may not immediately appear in environmental or satellite datasets.

For example:

```text
Model detects elevated risk
        +
Field officer reports new ground cracks
        ↓
Higher confidence for investigation
```

Similarly, field observations can provide information about:

* Newly occurring landslides
* Road blockages
* Local drainage issues
* Visible slope instability

In future versions, verified observations can also contribute to improving the underlying datasets and models.

---

# 🛰️ Data Sources

The project is designed to work with multiple geospatial and environmental sources.

Potential sources include:

* **Rainfall / environmental datasets**
* **DEM / elevation datasets**
* **SRTM / OpenTopography**
* **Sentinel-2 imagery**
* **NDVI-derived vegetation information**
* **Historical landslide inventories**
* **ISRO / GSI / Bhuvan datasets**
* **NASA COOLR as a fallback inventory source**
* **OpenStreetMap infrastructure data**
* **Field / citizen observations**

The exact source used for a particular feature depends on data availability, coverage, format and validation requirements.

---

# 📚 Historical Landslide Data

Historical landslide information provides spatial evidence about areas where landslides have previously occurred.

The project supports historical inventory processing and conversion into model-ready datasets.

Historical events can be used to:

* Identify spatial patterns
* Build susceptibility features
* Generate training labels
* Evaluate model predictions
* Compare model output against known events

### Training concept

The ML dataset can contain:

```text
Positive Samples
    ↓
Documented landslide locations

Negative / Background Samples
    ↓
Locations without documented landslide events
```

Negative/background samples must be constructed carefully because:

> **An area without a recorded landslide is not necessarily an area where no landslide occurred.**

Therefore, model evaluation and interpretation should account for inventory completeness and spatial sampling limitations.

---

# 🧪 Machine Learning Pipeline

The general ML workflow is:

```text
Historical Landslide Inventory
             +
Terrain Features
             +
Environmental Features
             +
NDVI / Vegetation Features
             +
Historical Susceptibility
             ↓
       Feature Engineering
             ↓
       Data Cleaning
             ↓
     Training Dataset
             ↓
      ML Model Training
             ↓
       Model Evaluation
             ↓
       Risk Prediction
             ↓
      SHAP Explanation
             ↓
        GIS Mapping
```

---

# 📈 Model Evaluation

Model performance should not be judged using accuracy alone.

Depending on the final training setup, useful evaluation metrics can include:

* Precision
* Recall
* F1-score
* ROC-AUC
* PR-AUC
* Confusion Matrix
* Spatial validation performance

Because geospatial data can be highly correlated spatially, random splitting can produce overly optimistic results.

Therefore, the project considers:

* **Spatial holdout regions**
* **Independent historical events**
* **Different time periods**
* **Additional landslide inventories**
* **Expert/geological validation**

These approaches can provide a more realistic assessment of model generalization.

---

# ⚠️ Spatial Data Leakage

Spatial data requires special attention during model evaluation.

Nearby pixels or locations can have very similar:

* Terrain
* Rainfall
* Vegetation
* Soil/environmental characteristics

If nearby locations appear in both training and testing datasets, the model may appear more accurate than it actually is.

Therefore, LandShield India aims to support **spatially separated validation** wherever sufficient data is available.

---

# 🗺️ Sikkim Pilot

The current prototype focuses on **Sikkim** as a pilot region before expanding the architecture across the wider Northeastern Region.

Sikkim provides a practical pilot environment for testing the complete workflow involving:

```text
Historical Landslides
        +
Terrain
        +
Environmental Conditions
        +
NDVI
        ↓
Machine Learning
        ↓
Risk Assessment
        ↓
GIS Visualization
```

Once the pipeline is validated and improved, the architecture can be extended to other NER states.

---

# 📁 Repository Structure

The repository contains data-processing scripts, geospatial workflows, model-related datasets and frontend/map components.

```text
LandShield-India/
│
├── data/
│   │
│   ├── environmental/
│   │   ├── gsi_environmental_features.csv
│   │   └── ...
│   │
│   ├── terrain/
│   │   ├── gsi_terrain_features.csv
│   │   └── ...
│   │
│   ├── ndvi/
│   │   └── gsi_ndvi_features.csv
│   │
│   ├── landslides/
│   │   ├── sikkim_2023_landslides.csv
│   │   └── sikkim_2023_landslides.geojson
│   │
│   └── gsi/
│       ├── gsi_dated_events.csv
│       ├── gsi_historical_susceptibility.csv
│       ├── gsi_landslide_inventory.csv
│       ├── gsi_landslide_inventory_normalized.csv
│       ├── gsi_model_training.csv
│       ├── gsi_ndvi_features.csv
│       ├── gsi_ner_training_table.csv
│       ├── gsi_pseudo_negative_samples.csv
│       ├── gsi_terrain_features.csv
│       ├── gsi_year_only_inventory.csv
│       ├── model_metrics.json
│       └── test_predictions.csv
│
├── frontend/
│   ├── css/
│   │   └── styles.css
│   │
│   ├── js/
│   │   ├── app.js
│   │   └── data.js
│   │
│   └── index.html
│
├── maps/
│   └── landslide_v1_risk_map.html
│
├── add_landslide_labels.py
├── build_gsi_training_table.py
├── build_india_environmental_features.py
├── clean_gsi_inventory.py
├── compute_historical_susceptibility_gsi.py
├── compute_hybrid_risk.py
├── extract_gsi_pdf.py
├── fetch_ndvi_gsi.py
├── fetch_terrain_features_gsi.py
├── make_model_risk_map.py
├── normalize_gsi_inventory.py
├── prepare_gsi_training_data.py
├── sample_pseudo_negatives.py
│
├── .gitignore
└── README.md
```

---

# 🐍 Core Processing Scripts

The repository contains separate scripts for different stages of the geospatial pipeline.

| Script                                     | Purpose                                           |
| ------------------------------------------ | ------------------------------------------------- |
| `add_landslide_labels.py`                  | Adds landslide-related labels to datasets         |
| `build_gsi_training_table.py`              | Builds a training table from GSI-derived features |
| `build_india_environmental_features.py`    | Prepares environmental feature layers             |
| `clean_gsi_inventory.py`                   | Cleans landslide inventory data                   |
| `compute_historical_susceptibility_gsi.py` | Computes historical susceptibility information    |
| `compute_hybrid_risk.py`                   | Combines risk-related components                  |
| `extract_gsi_pdf.py`                       | Extracts information from GSI PDF-based sources   |
| `fetch_ndvi_gsi.py`                        | Prepares NDVI-related features                    |
| `fetch_terrain_features_gsi.py`            | Prepares terrain-related features                 |
| `make_model_risk_map.py`                   | Generates model-based GIS risk maps               |
| `normalize_gsi_inventory.py`               | Normalizes landslide inventory information        |
| `prepare_gsi_training_data.py`             | Prepares ML-ready training data                   |
| `sample_pseudo_negatives.py`               | Generates pseudo-negative/background samples      |

---

# 🖥️ Frontend

The project includes a lightweight web-based frontend prototype.

```text
frontend/
│
├── index.html
├── css/
│   └── styles.css
│
└── js/
    ├── app.js
    └── data.js
```

The frontend is intended to provide a user-friendly interface for visualizing:

* Risk information
* GIS layers
* Locations
* Risk categories
* Impact information
* Decision-support outputs

The map component can be accessed through the generated HTML map under:

```text
maps/landslide_v1_risk_map.html
```

---

# 🛠️ Technology Stack

## Programming

* Python
* JavaScript
* HTML
* CSS

## Machine Learning

* XGBoost
* Random Forest
* Scikit-learn
* SHAP

## Geospatial Processing

* GeoPandas
* Rasterio
* GeoJSON
* GIS raster/vector processing

## Visualization

* GIS-based risk maps
* Interactive web maps
* GeoJSON layers
* HTML/JavaScript frontend

## Data

* Rainfall / environmental data
* DEM / elevation
* Slope
* NDVI
* Historical landslide inventories
* Infrastructure/geospatial data
* Field observations

---

# 🔄 End-to-End Architecture

```text
                 ┌──────────────────────────┐
                 │      DATA SOURCES        │
                 ├──────────────────────────┤
                 │ Rainfall / Environment   │
                 │ DEM / Elevation          │
                 │ Slope                    │
                 │ Historical Landslides    │
                 │ NDVI / Vegetation        │
                 │ GIS / Infrastructure     │
                 │ Field Observations       │
                 └────────────┬─────────────┘
                              │
                              ▼
                 ┌──────────────────────────┐
                 │ DATA CLEANING &          │
                 │ FEATURE ENGINEERING      │
                 └────────────┬─────────────┘
                              │
                              ▼
                 ┌──────────────────────────┐
                 │ MACHINE LEARNING MODEL   │
                 │ XGBoost / Random Forest  │
                 └────────────┬─────────────┘
                              │
                              ▼
                 ┌──────────────────────────┐
                 │     RISK ASSESSMENT      │
                 │      Score: 0–100        │
                 └────────────┬─────────────┘
                              │
                 ┌────────────┴────────────┐
                 ▼                         ▼
       ┌───────────────────┐     ┌───────────────────┐
       │ EXPLAINABLE AI    │     │   GIS MAPPING     │
       │      SHAP         │     │  Risk Heatmap     │
       └─────────┬─────────┘     └─────────┬─────────┘
                 │                         │
                 └────────────┬────────────┘
                              ▼
                 ┌──────────────────────────┐
                 │   IMPACT ASSESSMENT      │
                 ├──────────────────────────┤
                 │ Roads                    │
                 │ Settlements              │
                 │ Hospitals                │
                 │ Schools                  │
                 │ Critical Infrastructure  │
                 └────────────┬─────────────┘
                              │
                              ▼
                 ┌──────────────────────────┐
                 │ RESPONSE PRIORITIZATION  │
                 └────────────┬─────────────┘
                              │
                              ▼
                 ┌──────────────────────────┐
                 │   DECISION SUPPORT       │
                 └──────────────────────────┘
```

---

# 🔐 Responsible & Safe Use

LandShield India is currently a **prototype / research and hackathon project**.

It is intended to **support — not replace — professional disaster-management decisions**.

The platform should not replace:

* Government authorities
* Geological experts
* Official warning systems
* Field inspections
* Emergency-management protocols

AI-generated risk assessments should be combined with:

* Official information
* Expert knowledge
* Field verification
* Appropriate emergency-management procedures

before critical decisions are made.

---

# ⚠️ Limitations

The current prototype has several important limitations.

### 1. Historical Inventory Completeness

Not every landslide is necessarily recorded in available inventories.

Therefore:

> **No recorded event does not necessarily mean no landslide occurred.**

---

### 2. Data Availability

Different regions may have different levels of:

* Historical coverage
* Environmental data
* Terrain data
* Satellite availability
* Infrastructure information

---

### 3. Model Generalization

A model developed using one region or dataset may not automatically generalize to every part of the Northeastern Region.

Expansion should therefore involve:

* Additional training data
* Regional validation
* Independent testing
* Expert review

---

### 4. Prototype Risk Score

The 0–100 risk score is currently a decision-support representation.

It should not be interpreted as:

> **"There is an 82% chance of a landslide."**

For operational use, the model would require proper probability calibration and validation.

---

### 5. Field Verification

Remote sensing and environmental models cannot capture every local condition.

Ground observations remain important for operational disaster management.

---

# 🧪 Validation Strategy

Future validation should include multiple levels.

## Spatial Validation

Hold out geographic regions during testing.

```text
Training Regions
       ↓
Model
       ↓
Previously Unseen Region
       ↓
Evaluation
```

## Temporal Validation

Where dated historical events are available:

```text
Earlier Events
     ↓
Training

Later Events
     ↓
Testing
```

## Independent Inventory Validation

Predictions can be compared with additional landslide inventories that were not used during training.

## Expert Validation

Geological and disaster-management expertise can be used to evaluate whether high-risk areas are physically plausible.

---

# 🚀 Future Development

LandShield India is designed as a scalable architecture rather than a single static model.

## Phase 1 — Current Prototype

* Historical landslide processing
* Terrain feature generation
* Environmental feature generation
* NDVI integration
* ML training pipeline
* Risk scoring
* SHAP explanations
* GIS risk visualization
* Sikkim pilot
* Impact prioritization
* Frontend prototype

---

## Phase 2 — Advanced Monitoring

Potential future extensions include:

### 🛰️ Sentinel-1 InSAR

Use radar-based ground-deformation information to identify possible changes in terrain stability.

### 📷 Automated Image Analysis

Use computer vision to analyze field photographs for indicators such as:

* Ground cracks
* Landslide debris
* Road blockage
* Slope damage

### 📱 Multilingual Reporting

Allow citizens and field personnel to submit reports in regional languages.

### 📡 Offline Synchronization

Enable field personnel to collect observations in areas with limited connectivity and synchronize them when connectivity becomes available.

### 📈 Long-Term Risk Timelines

Track how risk indicators change over time.

### 🤖 Continuous Model Improvement

Validated observations can eventually be incorporated into future model-training cycles.

---

# 🌐 Scalability Across Northeast India

The current prototype focuses on Sikkim.

The long-term architecture is intended to support the wider NER.

Potential expansion can include:

```text
Sikkim
  ↓
Arunachal Pradesh
  ↓
Assam
  ↓
Meghalaya
  ↓
Nagaland
  ↓
Manipur
  ↓
Mizoram
  ↓
Tripura
```

The system architecture is designed so that the same processing and visualization pipeline can be adapted to different regions as suitable data becomes available.

---

# 📌 Project Status

**Status: Prototype / MVP Development**

The repository currently contains:

* ✅ Data-processing scripts
* ✅ Geospatial feature-generation workflows
* ✅ Machine-learning pipeline components
* ✅ Training datasets
* ✅ Model evaluation outputs
* ✅ Frontend prototype
* ✅ GIS risk-map generation
* ✅ Sikkim pilot data
* ✅ Historical susceptibility processing
* ✅ Environmental and terrain feature processing

The project is being developed toward a scalable landslide-risk monitoring and response platform for the **Northeastern Region of India**.

---

# 🎯 What Makes LandShield India Different?

Traditional approaches may focus primarily on:

> **"Where is the landslide hazard?"**

LandShield India aims to go one step further:

```text
WHERE?
  ↓
How risky is it?

WHY?
  ↓
What factors are contributing?

WHAT?
  ↓
What could be affected?

WHICH?
  ↓
Which location deserves priority?

VERIFY
  ↓
What are field officers/citizens observing?

ACT
  ↓
Where should response efforts be focused?
```

This creates a complete decision-support chain:

> ### **Risk → Explanation → Impact → Priority → Action**

---

# 🏆 Project Vision

Our vision is to build a scalable, explainable and human-assisted landslide decision-support platform that can help disaster-management teams move from fragmented datasets to a common spatial understanding of risk.

LandShield India aims to transform:

> **Geospatial Data → AI Insight → Actionable Decision Support**

---

# 👨‍💻 Team

## Team Six Bits

**Smart India Hackathon 2026**

**Problem Statement:** SIH26001
**Domain:** Disaster Management

---

# 📄 License

This project is currently developed as a **Smart India Hackathon prototype**.

License and deployment terms can be defined as the project progresses toward public or operational release.

---

# ⚠️ Disclaimer

LandShield India is a prototype and research project.

The system does **not** provide guaranteed landslide predictions or official emergency warnings.

Risk scores, maps and model outputs are intended for **research, demonstration and decision-support purposes** and should be interpreted together with official information, field observations and expert assessment.

---

# ⭐ LandShield India

### **From Landslide Risk to Actionable Response**

> **Predict → Verify → Assess Impact → Prioritize → Alert**

**Built by Team Six Bits for Smart India Hackathon 2026**

```

### One important change I made

I deliberately **didn't overclaim the AI**. For example, instead of saying:

> `82/100 = 82% chance of landslide`

the README clearly says it's a **prototype risk indicator**. That's much safer and more professional for judges, because your current repository is a prototype and your screenshots themselves already acknowledge that limitation.

Also, this version covers the things visible in your repository: **GSI processing, Sikkim data, pseudo-negative sampling, historical susceptibility, environmental/terrain/NDVI features, ML, SHAP, GIS mapping, frontend, impact prioritization, human verification, validation, limitations and future scope.**
```
