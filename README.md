# HomeValue India: House Price Prediction using Machine Learning

A capstone project that predicts **apartment prices in five Indian metros** (Mumbai, Delhi NCR, Bengaluru,
Chennai, Hyderabad) from city, locality, area, BHK, new vs resale status and amenities. It ships as a
**FastAPI backend** and a **responsive web frontend**, with prices in ₹ lakh/crore, a calibrated price
range and a home-loan EMI calculator. See [PLAN.md](PLAN.md) for the full project plan.

## Results (held-out test set: 1,616 listings never seen in training)

| Metric | Value |
|---|---|
| **Median error** | **6.5%** |
| Mean absolute % error (MAPE) | 11.5% |
| Predictions within ±10% / ±20% | 63% / 84% |
| R² on log price / on ₹ | 0.929 / 0.869 |
| 80% price range: share of actual prices inside | 81.5% (well calibrated) |

**Model comparison (5-fold cross-validation, training set):**

| Model | Median error | MAPE | Within ±10% | R² (log) |
|---|---|---|---|---|
| **Stacked Ensemble (tuned GB + tuned Extra Trees → Ridge)** | **6.9%** | **12.1%** | **61%** | **0.922** |
| Extra Trees | 6.9% | 12.1% | 61% | 0.919 |
| Random Forest | 7.4% | 12.5% | 59% | 0.920 |
| Gradient Boosting | 8.2% | 13.2% | 57% | 0.916 |
| Decision Tree | 9.4% | 15.6% | 52% | 0.884 |
| Baseline: locality avg ₹/sq ft × area | 10.1% | 16.0% | 50% | 0.868 |
| Linear Regression | 10.7% | 15.8% | 47% | 0.887 |

**Error by city (test set):** Bengaluru 3.7% · Chennai 5.0% · Hyderabad 7.2% · Delhi NCR 8.2% · Mumbai 13.0%.
Mumbai is hardest: it has the most localities (235) and the fewest listings per locality.

**What drives price (permutation importance):** area ≫ location (city + locality) > locality within city
≫ amenities > BHK > new/resale.

## Dataset and data-quality audit
*Housing Prices in Metropolitan Areas of India* (Makaan.com listings, Kaggle): 32,963 listings, 6 metros,
40 columns (price, area, locality, BHK, resale, 35 amenity flags).

**Key finding:** 69% of rows have every amenity coded `9` ("not recorded"). In those rows **price is
essentially unrelated to area** (log correlation 0.21, against 0.77 in recorded rows). The scraped prices
are misaligned with their listings. Training on them capped R² at about 0.45. Removing them raised it to about 0.92.
See `reports/figures/01_data_quality_audit.png`.

| Step | Rows left |
|---|---|
| Raw listings (6 metros) | 32,963 |
| Drop rows with amenities not recorded | 10,093 |
| Drop Kolkata (only 75 reliable rows) | 10,018 |
| Drop exact duplicates | 8,171 |
| Drop implausible ₹/sq ft (outside ₹1,500–₹75,000) | 8,167 |
| Drop implausible area per BHK (outside 250–2,500 sq ft) | 8,076 |

| City | Listings | Localities | Median price | Median ₹/sq ft |
|---|---|---|---|---|
| Bengaluru | 1,617 | 105 | ₹70.1 L | ₹5,236 |
| Chennai | 1,767 | 138 | ₹58.6 L | ₹5,391 |
| Delhi NCR | 1,629 | 102 | ₹1.00 Cr | ₹7,750 |
| Hyderabad | 1,912 | 239 | ₹79.0 L | ₹5,115 |
| Mumbai | 1,151 | 235 | ₹1.00 Cr | ₹9,659 |

## Methodology
1. **Cleaning**: the audit above. Locality names are normalised (whitespace, case; abbreviations
   like *RR Nagar*, *OMR* and *HSR* are kept).
2. **Target**: the model learns **log(price per sq ft)**, and price = rate × area. This mirrors how the
   Indian market quotes prices and handles the heavy price skew (₹20 L to ₹15+ Cr).
3. **Features**: city (one-hot), locality (**cross-fitted target encoding**, so no target leakage),
   area, log area, area per BHK, BHK, resale flag, 35 amenity flags and amenity count.
4. **Split**: 80/20, stratified by city. The test set is used once at the end.
5. **Models**: a broker-style baseline, Linear Regression, Decision Tree, Random Forest, Extra Trees and
   Gradient Boosting, compared with 5-fold CV. Gradient Boosting and Extra Trees are tuned with
   RandomizedSearchCV (25 candidates each), then **stacked** with a Ridge meta-model.
6. **Uncertainty**: an 80% price range from the quantiles of out-of-fold errors (multiplicative).
7. **Evaluation**: test metrics overall and per city, predicted vs actual, error distribution, and
   grouped permutation importance.

## Web app
- **Estimate**: city and locality picker (with each locality's median ₹/sq ft), area slider, BHK, new or
  resale, and 35 amenities in 4 groups with presets (Basic / Gated / Premium). Estimates update live.
- **Result**: price in ₹ lakh/crore with full Indian digit grouping (₹1,38,89,427), ₹/sq ft compared with
  the locality median, the 80% range, and warnings for unknown or sparse localities.
- **EMI calculator**: down payment, interest rate and tenure, giving the monthly EMI and total interest.
- **Accuracy dashboard**: metric tiles, model comparison, error by city and feature importance, each
  with hover tooltips and a table view.
- **Insights**: EDA charts in a gallery. **Method**: the cleaning audit, modelling and limitations.
- Light and dark themes, works on mobile. REST API documentation is auto-generated at `/docs`.

## Project structure
```
├── api.py                  # FastAPI: /api/predict, /api/options, /api/model-info, serves frontend
├── frontend/               # index.html, styles.css, app.js (no build step)
├── src/
│   ├── config.py           # paths, cities, amenity names/labels, cleaning thresholds
│   ├── data.py             # load raw CSVs, clean, write audit report
│   ├── features.py         # FeatureBuilder, encoders, PricePerSqftRegressor
│   ├── metrics.py          # shared % error / R² metrics
│   ├── eda.py              # exploratory figures
│   ├── train.py            # CV comparison, tuning, stacking, save model
│   ├── evaluate.py         # test metrics, per-city errors, permutation importance
│   └── predict.py          # prediction service + CLI
├── tests/                  # pytest: cleaning rules, model sanity, API validation
├── data/raw/               # original 6 city CSVs
├── models/                 # trained model, metadata, locality stats
└── reports/                # figures/, model_comparison.csv, city summaries, cleaning audit
```

## How to run
```bash
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt

python -m src.data        # 1. clean data + audit report
python -m src.eda         # 2. exploratory figures
python -m src.train       # 3. compare, tune, stack, save model (~5 min)
python -m src.evaluate    # 4. test-set metrics + figures
pytest                    # 5. run tests

uvicorn api:app --reload  # 6. open http://127.0.0.1:8000  (API docs: /docs)
```

Command-line prediction:
```bash
python -m src.predict --city Bangalore --locality "Whitefield Hope Farm Junction" --area 1450 --bhk 3 \
    --amenities LiftAvailable CarParking Gymnasium SwimmingPool
```

API example:
```bash
curl -X POST http://127.0.0.1:8000/api/predict -H "Content-Type: application/json" \
  -d '{"city":"Mumbai","locality":"Thane West","area_sqft":1050,"bhk":2,"resale":true,"amenities":["LiftAvailable","CarParking"]}'
```

## Limitations and future work
- These are **asking prices** from listings (about 2021), not registered transaction prices. Adjust for appreciation.
- Kolkata is excluded, and localities absent from the data fall back to city-level pricing.
- Locality names are fragmented in the source (for example "Whitefield" vs "Whitefield Hope Farm Junction").
  Geocoding localities to latitude/longitude would merge them and allow distance-based features.
- Future work: recent data (for example state registration records), floor/age/facing features, SHAP
  explanations per prediction, and cloud deployment (Render/Railway) with Docker.
