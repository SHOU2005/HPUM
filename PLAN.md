# Capstone Plan: House Price Prediction for the Indian Market using Machine Learning

## 1. Problem Statement
Home buyers, sellers and brokers in Indian metros price property mostly by word of mouth and
"rate per sq ft" rules of thumb. The goal is to **predict the market price (₹) of an apartment**
from its city, locality, carpet/super area, BHK, new vs resale status and amenities, and to show an
honest likely price range, so users can sanity-check a listing. This is a **supervised regression** problem.

## 2. Dataset
**Housing Prices in Metropolitan Areas of India** (Makaan.com listings, published on Kaggle; mirrored
on GitHub). It has 32,963 listings across 6 metros: Mumbai, Delhi NCR, Bangalore, Chennai, Hyderabad, Kolkata.

| Column | Meaning |
|---|---|
| Price | Listing price (₹), the **target** |
| Area | Area in sq ft |
| Location | Locality (about 1,800 unique) |
| No. of Bedrooms | BHK |
| Resale | 1 = resale, 0 = new property |
| 35 amenity flags | Gym, Lift, Car parking, Swimming pool, 24x7 security, ... (1/0, **9 = not recorded**) |

### Data-quality audit (key finding)
- 69% of rows have every amenity coded `9` (not recorded).
- In those rows the price is essentially unrelated to area (correlation 0.1–0.3), while in rows with
  amenities recorded it is 0.85–0.90. The scraped prices in the `9` rows are misaligned with their
  listings, so **they are excluded**.
- Kolkata has only 75 trustworthy rows, too few to model, so the model covers **5 metros**.
- Drop exact duplicates. Drop implausible listings: price per sq ft outside ₹1,500–₹75,000, or
  area per BHK outside 250–2,500 sq ft.
- Result: about 8,000 clean listings, 5 cities, about 800 localities.

## 3. Project Structure
```
HPUM/
├── PLAN.md, README.md, requirements.txt
├── data/raw/                 # original 6 city CSVs (untouched)
├── src/
│   ├── config.py             # paths, cities, amenity names and labels
│   ├── data.py               # load + clean + audit report
│   ├── features.py           # feature engineering, encoders, price-per-sqft wrapper
│   ├── eda.py                # exploratory analysis -> reports/figures
│   ├── train.py              # compare, tune, stack, save best model
│   ├── evaluate.py           # test-set metrics, per-city errors, importance
│   └── predict.py            # prediction service (API + CLI)
├── api.py                    # FastAPI backend (REST API + serves frontend)
├── frontend/                 # HTML/CSS/JS web app
├── tests/                    # pytest tests for data, model and API
├── models/                   # saved model + metadata
└── reports/                  # figures, comparison tables, cleaning audit
```

## 4. Methodology
1. **EDA**: listings per city, ₹/sq ft by city, price vs area, priciest localities, amenity
   premiums, and a data-quality plot (clean vs corrupted rows).
2. **Feature engineering**: log area, area per BHK, amenity count, city one-hot, and **locality target
   encoding** (scikit-learn `TargetEncoder`, cross-fitted, so there is no leakage).
3. **Target**: the model predicts **log(price per sq ft)**, and price = predicted rate × area. This
   matches how the Indian market quotes prices and handles the heavy price skew.
4. **Split**: 80% train / 20% test (stratified by city, `random_state=42`). The test set is used once.
5. **Models (5-fold CV)**: locality-average baseline, Linear Regression, Decision Tree, Random Forest,
   Extra Trees, Gradient Boosting, then **tuning** (RandomizedSearchCV) and a **stacked ensemble**.
6. **Metrics**: MAPE, median % error, share within ±10% and ±20%, R² (log scale and ₹), MAE (₹ lakh).
   Plus a calibrated **80% price range** from out-of-fold errors.
7. **Evaluation**: test-set metrics, error by city, predicted vs actual, residuals, grouped
   permutation importance (locality, area, city, amenities, ...).
8. **Deployment**: FastAPI REST API (`/api/predict`, `/api/options`, `/api/model-info`, auto docs at
   `/docs`) plus a responsive web frontend with a city/locality picker, BHK, area, amenities,
   prices in ₹ lakh/crore, an EMI estimate and model-performance dashboards.
9. **Testing**: pytest for the cleaning rules, model sanity checks and API validation.

## 5. Success Criteria
- The ML model clearly beats the "locality average ₹/sq ft × area" baseline.
- Target: **median error ≤ 10%** and **R² (log) ≥ 0.85** on the held-out test set.
- Fully reproducible: running `eda`, `train` and `evaluate` regenerates every artefact.

## 6. Limitations (to state in the report)
Listing (asking) prices, not registered sale prices. The data is a snapshot from about 2021, so it
should be adjusted for appreciation. It covers only localities present in the data. Kolkata is excluded.
