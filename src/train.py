"""Compare models with cross-validation, tune the best two, stack them, save the winner.

Run:  python -m src.train
"""
import json
import time

import joblib
import numpy as np
import pandas as pd
from scipy.stats import loguniform, randint, uniform
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import (ExtraTreesRegressor, HistGradientBoostingRegressor,
                              RandomForestRegressor, StackingRegressor)
from sklearn.linear_model import LinearRegression, RidgeCV
from sklearn.model_selection import KFold, RandomizedSearchCV, cross_val_predict, train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler, TargetEncoder
from sklearn.tree import DecisionTreeRegressor

from src.config import (AMENITIES, CITIES, CV_FOLDS, INPUT_FEATURES, LOCALITIES_PATH, METADATA_PATH,
                        MODEL_PATH, RANDOM_STATE, REPORTS_DIR, SPLIT_PATH, TARGET, TEST_SIZE)
from src.data import load_clean
from src.features import FeatureBuilder, PricePerSqftRegressor, encoder
from src.metrics import regression_metrics

ENSEMBLE_NAME = "Stacked Ensemble"


def make_model(estimator, scale=False):
    """Raw inputs -> engineered features -> encoders -> estimator, trained on log(₹/sq ft)."""
    steps = [("features", FeatureBuilder()), ("encode", encoder())]
    if scale:
        steps.append(("scale", StandardScaler()))
    return PricePerSqftRegressor(Pipeline(steps + [("model", estimator)]))


def locality_baseline():
    """What a broker does: locality's average ₹/sq ft × area. Nothing else."""
    return PricePerSqftRegressor(Pipeline([
        ("features", FeatureBuilder()),
        ("encode", ColumnTransformer([("locality", TargetEncoder(random_state=RANDOM_STATE), ["LocalityKey"])])),
        ("model", LinearRegression()),
    ]))


def candidate_models():
    return {
        "Baseline: locality avg ₹/sq ft": locality_baseline(),
        "Linear Regression": make_model(LinearRegression(), scale=True),
        "Decision Tree": make_model(DecisionTreeRegressor(max_depth=10, min_samples_leaf=5,
                                                          random_state=RANDOM_STATE)),
        "Random Forest": make_model(RandomForestRegressor(n_estimators=300, max_features=0.5,
                                                         min_samples_leaf=2, n_jobs=-1,
                                                         random_state=RANDOM_STATE)),
        "Extra Trees": make_model(ExtraTreesRegressor(n_estimators=400, max_features=0.5,
                                                      min_samples_leaf=2, n_jobs=-1,
                                                      random_state=RANDOM_STATE)),
        "Gradient Boosting": make_model(HistGradientBoostingRegressor(max_iter=600, learning_rate=0.05,
                                                                      random_state=RANDOM_STATE)),
    }


SEARCH_SPACES = {
    "Gradient Boosting": {
        "estimator__model__learning_rate": loguniform(0.02, 0.15),
        "estimator__model__max_iter": randint(300, 1200),
        "estimator__model__max_leaf_nodes": randint(15, 63),
        "estimator__model__min_samples_leaf": randint(5, 40),
        "estimator__model__l2_regularization": loguniform(1e-3, 3.0),
    },
    "Extra Trees": {
        "estimator__model__n_estimators": randint(300, 800),
        "estimator__model__max_features": uniform(0.3, 0.6),
        "estimator__model__min_samples_leaf": randint(1, 5),
    },
}


def tune(name, model, X, y, cv):
    search = RandomizedSearchCV(model, SEARCH_SPACES[name], n_iter=25, cv=cv,
                                scoring="neg_root_mean_squared_error", n_jobs=-1,
                                random_state=RANDOM_STATE)
    search.fit(X, y)
    params = {k.split("__")[-1]: (v.item() if isinstance(v, np.generic) else v)
              for k, v in search.best_params_.items()}
    print(f"  {name:20s} best CV RMSE(log) {-search.best_score_:.4f}  {params}")
    return search.best_estimator_, params


def locality_stats(train_df):
    """Per-city locality list for the UI: listings and median ₹/sq ft (training rows only)."""
    g = (train_df.assign(ppsf=train_df["Price"] / train_df["Area"])
                 .groupby(["City", "Location"])
                 .agg(listings=("ppsf", "size"), median_ppsf=("ppsf", "median"))
                 .reset_index())
    return {c: [{"name": r.Location, "listings": int(r.listings), "median_ppsf": round(float(r.median_ppsf))}
                for r in g[g["City"] == c].sort_values("listings", ascending=False).itertuples()]
            for c in CITIES}


def main():
    t_start = time.time()
    df = load_clean()
    X, y = df[INPUT_FEATURES], np.log(df[TARGET])
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=TEST_SIZE, random_state=RANDOM_STATE, stratify=df["City"])
    print(f"Train: {len(X_train):,}  Test: {len(X_test):,}")
    # keep the untouched test split so evaluate.py scores exactly these rows
    X_test.assign(**{TARGET: np.exp(y_test).round()}).to_csv(SPLIT_PATH, index=False)

    cv = KFold(CV_FOLDS, shuffle=True, random_state=RANDOM_STATE)
    models = candidate_models()
    oof, rows = {}, []

    def record(name, pred, seconds):
        oof[name] = pred
        m = regression_metrics(y_train, pred)
        rows.append({"Model": name, **m, "Time (s)": round(seconds, 1)})
        print(f"  {name:32s} MAPE={m['mape']:.3f}  median err={m['median_ape']:.3f}  "
              f"within 10%={m['within_10']:.2f}  R2(log)={m['r2_log']:.4f}")

    print("\n[1/3] Cross-validating candidate models")
    for name, model in models.items():
        t0 = time.time()
        record(name, cross_val_predict(model, X_train, y_train, cv=cv, n_jobs=-1), time.time() - t0)

    print("\n[2/3] Tuning Gradient Boosting and Extra Trees (RandomizedSearchCV)")
    tuned, tuned_params = {}, {}
    for name in SEARCH_SPACES:
        tuned[name], tuned_params[name] = tune(name, models[name], X_train, y_train, cv)

    print(f"\n[3/3] Cross-validating {ENSEMBLE_NAME} (tuned GB + tuned Extra Trees -> Ridge)")
    # Stack the inner pipelines on log(₹/sq ft); the outer wrapper converts back to price.
    ensemble = PricePerSqftRegressor(StackingRegressor(
        estimators=[("gradient_boosting", tuned["Gradient Boosting"].estimator),
                    ("extra_trees", tuned["Extra Trees"].estimator)],
        final_estimator=RidgeCV(), cv=CV_FOLDS, n_jobs=1))
    t0 = time.time()
    record(ENSEMBLE_NAME, cross_val_predict(ensemble, X_train, y_train, cv=cv, n_jobs=-1), time.time() - t0)

    results = pd.DataFrame(rows).sort_values("rmse_log").reset_index(drop=True)
    results.to_csv(REPORTS_DIR / "model_comparison.csv", index=False)
    print("\n" + results[["Model", "mape", "median_ape", "within_10", "r2_log", "r2_inr", "mae_lakh"]]
          .round(4).to_string(index=False))

    best_name = results.loc[0, "Model"]
    final = ensemble if best_name == ENSEMBLE_NAME else tuned.get(best_name, models[best_name])
    print(f"\nBest model: {best_name} — fitting on full training set")
    final.fit(X_train, y_train)
    joblib.dump(final, MODEL_PATH, compress=3)  # ~3x smaller, keeps the file under GitHub's 100 MB limit

    # Errors are multiplicative, so the range is too: 80% of out-of-fold
    # predictions fell within [pred × low, pred × high].
    lo, hi = np.quantile(y_train - oof[best_name], [0.10, 0.90])
    train_df = df.loc[X_train.index]
    meta = {
        "model_name": best_name,
        "ensemble_members": ["Gradient Boosting (tuned)", "Extra Trees (tuned)"] if best_name == ENSEMBLE_NAME else None,
        "tuned_params": tuned_params,
        "cv_metrics": {k: float(v) for k, v in results.loc[0].items() if k not in ("Model", "Time (s)")},
        "interval": {"coverage": 0.8, "low_factor": float(np.exp(lo)), "high_factor": float(np.exp(hi))},
        "comparison": results.round(4).to_dict(orient="records"),
        "n_train": len(X_train),
        "n_test": len(X_test),
        "cities": CITIES,
        "amenities": AMENITIES,
        "area_range": [float(train_df["Area"].min()), float(train_df["Area"].max())],
        "bhk_range": [int(train_df["BHK"].min()), int(train_df["BHK"].max())],
    }
    METADATA_PATH.write_text(json.dumps(meta, indent=2, ensure_ascii=False))
    LOCALITIES_PATH.write_text(json.dumps(locality_stats(train_df), ensure_ascii=False))
    print(f"Saved model -> {MODEL_PATH}  (total {time.time() - t_start:.0f}s)")


if __name__ == "__main__":
    main()
