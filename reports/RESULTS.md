# Experimental Results

HomeValue India: apartment price prediction for five Indian metros.
Results as of 29 October 2026. All numbers come from the saved files in `models/` and `reports/`.

---

## 1. Summary

- **Final model:** stacked ensemble of tuned Gradient Boosting and tuned Extra Trees, combined with Ridge.
- **Held-out test set:** 1,616 listings, used once. Median error **6.5%**, R² (log) **0.929**, 81.5% of actual prices inside the 80% range.
- **Beats the market rule:** the locality-average "₹ per sq ft × area" baseline has a median error of 10.1% in cross-validation. The stacked model has 6.9%.
- **Weakest city:** Mumbai, with a median error of 13.0%. It is the only city above the 10% target.

## 2. Experimental setup

| Item | Value |
|---|---|
| Source | Makaan.com listings, Kaggle, six metros, 32,963 raw rows |
| Cleaned dataset | 8,076 listings, five cities, about 800 localities |
| Train / test split | 6,460 / 1,616, stratified by city, `random_state=42` |
| Target | log(₹ per sq ft); price = predicted rate × area |
| Validation | Five-fold cross-validation on the training set; test set used once |
| Hardware and software | scikit-learn, pandas, FastAPI; full run is about five minutes |

### Cleaning steps

| Step | Rows after step | Rows removed | Reason |
|---|---|---|---|
| Raw listings | 32,963 | | Six metros |
| Drop listings with all amenities coded 9 | 10,093 | 22,870 | Prices misaligned with listings (see section 6) |
| Drop Kolkata | 10,018 | 75 | Too few reliable listings |
| Drop exact duplicates | 8,171 | 1,847 | Same listing scraped more than once |
| Drop ₹/sq ft outside ₹1,500–₹75,000 | 8,167 | 4 | Implausible rates |
| Drop area per BHK outside 250–2,500 sq ft, or BHK above 6 | 8,076 | 91 | Implausible layouts |

Source: `reports/data_cleaning_audit.json`.

### Final dataset by city

| City | Listings | Localities | Median price | Median ₹/sq ft |
|---|---|---|---|---|
| Bengaluru | 1,617 | 105 | ₹70.1 lakh | ₹5,236 |
| Chennai | 1,767 | 138 | ₹58.6 lakh | ₹5,391 |
| Delhi NCR | 1,629 | 102 | ₹1.00 crore | ₹7,750 |
| Hyderabad | 1,912 | 239 | ₹79.0 lakh | ₹5,115 |
| Mumbai | 1,151 | 235 | ₹1.00 crore | ₹9,659 |

Source: `reports/city_summary.csv`.

## 3. Model comparison (five-fold cross-validation, training set)

| Model | Median error | MAPE | Within ±10% | Within ±20% | R² (log) | R² (₹) | MAE (₹ lakh) | Train time (s) |
|---|---|---|---|---|---|---|---|---|
| **Stacked ensemble** | **6.9%** | **12.1%** | **61.3%** | **82.9%** | **0.922** | 0.800 | 15.5 | 44.3 |
| Extra Trees (tuned) | 6.9% | 12.1% | 61.0% | 82.4% | 0.919 | 0.770 | 15.9 | 2.8 |
| Random Forest | 7.4% | 12.5% | 59.1% | 81.5% | 0.920 | 0.803 | 16.0 | 3.3 |
| Gradient Boosting (tuned) | 8.2% | 13.2% | 56.9% | 80.6% | 0.916 | 0.831 | 16.4 | 2.0 |
| Decision Tree | 9.4% | 15.6% | 52.2% | 76.1% | 0.884 | 0.755 | 19.8 | 0.2 |
| Baseline: locality ₹/sq ft × area | 10.1% | 16.0% | 49.7% | 74.2% | 0.868 | 0.709 | 20.3 | 1.1 |
| Linear Regression | 10.7% | 15.8% | 47.4% | 73.3% | 0.887 | 0.781 | 20.0 | 0.8 |

Source: `reports/model_comparison.csv`. Gradient Boosting and Extra Trees were tuned with RandomizedSearchCV (25 candidates each).

**Reading the table:** the stacked ensemble is the best model, but its margin over tuned Extra Trees is small (R² 0.922 vs 0.919, within ±10% 61.3% vs 61.0%). Extra Trees trains in a fraction of the time. The stacked model was kept because it is the most accurate, and the cost is still under a minute.

### Chosen hyperparameters

| Component | Settings |
|---|---|
| Gradient Boosting | learning rate 0.0267, 430 iterations, 36 max leaf nodes, min samples per leaf 6, L2 regularisation 0.0145 |
| Extra Trees | 685 trees, max features 0.80, min samples per leaf 2 |
| Meta-model | Ridge regression on the two models' predictions |

Source: `models/model_metadata.json`.

## 4. Test-set results (held-out, used once)

| Metric | Value |
|---|---|
| Listings | 1,616 |
| Median % error | **6.5%** |
| Mean % error (MAPE) | 11.5% |
| Within ±10% | 63.1% |
| Within ±20% | 83.8% |
| R² (log price) | **0.929** |
| R² (₹ price) | 0.869 |
| RMSE (log scale) | 0.190 |
| MAE | ₹14.0 lakh |
| 80% range coverage | 81.5% (target 80%) |

The test-set numbers are slightly better than the cross-validation numbers (median error 6.5% vs 6.9%, R² 0.929 vs 0.922). The test set is a single split, so the cross-validation figures are the basis for model selection, and the test set is used only to report the final result.

## 5. Results by city (test set)

| City | Listings | Median error | MAPE | Within ±10% | Within ±20% | R² (log) | MAE (₹ lakh) |
|---|---|---|---|---|---|---|---|
| Bengaluru | 323 | **3.7%** | 5.6% | 81.7% | 96.3% | 0.981 | 5.9 |
| Chennai | 354 | 5.0% | 7.9% | 72.3% | 91.0% | 0.960 | 7.9 |
| Hyderabad | 383 | 7.2% | 14.0% | 57.2% | 79.4% | 0.886 | 14.5 |
| Delhi NCR | 326 | 8.2% | 12.3% | 57.4% | 82.8% | 0.946 | 14.9 |
| Mumbai | 230 | 13.0% | 20.3% | 40.4% | 63.9% | 0.863 | 32.8 |

Source: `reports/test_metrics_by_city.csv`.

**Why Mumbai is hardest:** it has the most localities per listing (235 localities for 1,151 listings, about 0.20 per listing, against 0.13 in Hyderabad and 0.08 in Chennai), so each locality has few examples to learn from. Mumbai also has the highest prices, so the same percentage error means a larger rupee error (₹32.8 lakh MAE).

## 6. Data-quality finding

Listings whose amenities are all coded `9` make up 69% of the raw data. In those rows, the log correlation between price and area is 0.21. In rows with amenities recorded, it is 0.77.

| Listings | Log correlation (price, area) |
|---|---|
| Amenities recorded | 0.775 |
| Amenities not recorded (code 9) | 0.210 |

This indicates that the prices in the unrecorded rows do not match their listings, so the project excludes them. Source: `reports/data_cleaning_audit.json`.

Figure: `reports/figures/01_data_quality_audit.png`.

## 7. Calibrated price range

Each prediction comes with an 80% range, built from the out-of-fold errors on the training set:

- Lower bound = prediction × 0.833
- Upper bound = prediction × 1.196

On the test set, 81.5% of actual prices fall inside the range, close to the 80% target.

## 8. What drives the price

Grouped permutation importance on the test set. Each group is shuffled together and the increase in error is measured.

| Feature group | Importance | Std. dev. |
|---|---|---|
| Area (sq ft) | 0.883 | 0.019 |
| Location (city + locality) | 0.611 | 0.012 |
| Locality within city | 0.287 | 0.012 |
| All amenities | 0.040 | 0.002 |
| BHK | 0.018 | 0.001 |
| New vs resale | 0.009 | 0.001 |

The location group includes the locality-within-city feature, so the importances overlap and should not be added up. Among individual amenities, Clubhouse (0.004), Vaastu compliant (0.003) and piped gas (0.003) rank highest, and all are small.

Source: `models/model_metadata.json`. Figure: `reports/figures/10_feature_importance.png`.

## 9. Limitations of these results

- **Asking prices, not transaction prices.** Listings from about 2021 are seller asking prices. Accuracy against registered sale prices is not known.
- **One data source and one snapshot.** Results may not carry over to other years or portals.
- **Single test split.** The test set was used once with a fixed seed. Repeated splits would give a confidence interval; this has not been done.
- **Locality coverage.** Localities not in the training data fall back to city-level pricing, so their estimates are less reliable.
- **Missing features.** Age, floor, facing and exact coordinates are not in the data.

## 10. Figures

| File | Shows |
|---|---|
| `figures/01_data_quality_audit.png` | Recorded vs unrecorded amenities: price vs area |
| `figures/02_listings_per_city.png` | Listings by city |
| `figures/03_price_per_sqft_by_city.png` | ₹/sq ft distribution by city |
| `figures/04_price_vs_area.png` | Price vs area |
| `figures/05_top_localities.png` | Priciest localities |
| `figures/06_bhk_and_resale.png` | BHK and resale patterns |
| `figures/07_amenity_premium.png` | Price premium for each amenity |
| `figures/08_predicted_vs_actual.png` | Test-set predictions vs actual prices |
| `figures/09_errors.png` | Error distribution and by city |
| `figures/10_feature_importance.png` | Grouped permutation importance |

## 11. Reproducing these results

```bash
python -m src.data        # cleaning and audit
python -m src.eda         # exploratory figures
python -m src.train       # comparison, tuning, stacking, saved model
python -m src.evaluate    # test metrics, per-city table, figures
```

The test-set and per-city numbers in this file come from the saved outputs of the last `python -m src.evaluate` run. The full pipeline was not re-run for this write-up.
