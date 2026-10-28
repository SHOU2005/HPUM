"""Evaluate the saved model on the held-out test set.

Run:  python -m src.evaluate
"""
import json

import joblib
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns

from src.config import (AMENITIES, AMENITY_LABELS, CITIES, FIGURES_DIR, INPUT_FEATURES, METADATA_PATH,
                        MODEL_PATH, REPORTS_DIR, SPLIT_PATH, TARGET)
from src.metrics import regression_metrics

sns.set_theme(style="whitegrid", font="DejaVu Sans")  # bundled with matplotlib, has the ₹ glyph

# Locality is keyed by city, so shuffling city alone would also scramble locality.
# Location is measured jointly, and locality separately by shuffling only within each city.
IMPORTANCE_GROUPS = {"Location (city + locality)": ["City", "Location"],
                     "Locality within city": ["Location"], "Area (sq ft)": ["Area"],
                     "BHK": ["BHK"], "New vs resale": ["Resale"], "All amenities": AMENITIES}
WITHIN_CITY = {"Locality within city"}


def grouped_permutation_importance(model, X, y_log, n_repeats=5, seed=0):
    """Drop in R² (log price) when a group of columns is shuffled together.

    Grouping keeps related inputs (e.g. 35 amenity flags) from hiding each other's importance.
    """
    rng = np.random.default_rng(seed)
    base = regression_metrics(y_log, model.predict(X))["r2_log"]
    groups = {**IMPORTANCE_GROUPS, **{AMENITY_LABELS[a]: [a] for a in AMENITIES}}
    out = []
    for name, cols in groups.items():
        drops = []
        for _ in range(n_repeats):
            Xp = X.copy()
            if name in WITHIN_CITY:
                for idx in X.groupby("City").indices.values():
                    Xp.iloc[idx, Xp.columns.get_indexer(cols)] = X[cols].to_numpy()[rng.permutation(idx)]
            else:
                Xp[cols] = X[cols].to_numpy()[rng.permutation(len(X))]
            drops.append(base - regression_metrics(y_log, model.predict(Xp))["r2_log"])
        out.append({"feature": name, "importance": float(np.mean(drops)), "std": float(np.std(drops)),
                    "kind": "group" if name in IMPORTANCE_GROUPS else "amenity"})
    return out


def main():
    model = joblib.load(MODEL_PATH)
    test = pd.read_csv(SPLIT_PATH)
    X, y_log = test[INPUT_FEATURES], np.log(test[TARGET])
    pred_log = model.predict(X)
    price, pred = test[TARGET].to_numpy(), np.exp(pred_log)

    meta = json.loads(METADATA_PATH.read_text())
    iv = meta["interval"]
    metrics = regression_metrics(y_log, pred_log)
    metrics["interval_coverage"] = float(((price >= pred * iv["low_factor"]) &
                                          (price <= pred * iv["high_factor"])).mean())
    by_city = {c: regression_metrics(y_log[test["City"] == c], pred_log[test["City"] == c]) | {
        "n": int((test["City"] == c).sum())} for c in CITIES}

    print(f"Test listings: {len(test):,}")
    print(f"  Median % error   : {metrics['median_ape']:.1%}")
    print(f"  Mean % error     : {metrics['mape']:.1%}")
    print(f"  Within ±10% / 20%: {metrics['within_10']:.1%} / {metrics['within_20']:.1%}")
    print(f"  R² (log / ₹)     : {metrics['r2_log']:.4f} / {metrics['r2_inr']:.4f}")
    print(f"  MAE              : ₹{metrics['mae_lakh']:.1f} lakh")
    print(f"  80% range covers : {metrics['interval_coverage']:.1%} of test listings")
    print("\nBy city:")
    print(pd.DataFrame(by_city).T[["n", "median_ape", "mape", "within_10", "r2_log"]].round(3).to_string())

    # Predicted vs actual
    fig, ax = plt.subplots(figsize=(7, 7))
    for c in CITIES:
        m = test["City"] == c
        ax.scatter(price[m] / 1e5, pred[m] / 1e5, s=6, alpha=0.5, label=c)
    lim = [15, max(price.max(), pred.max()) / 1e5 * 1.1]
    ax.plot(lim, lim, "k--", lw=1, label="Perfect prediction")
    ax.set(xscale="log", yscale="log", xlim=lim, ylim=lim, xlabel="Actual price (₹ lakh)",
           ylabel="Predicted price (₹ lakh)",
           title=f"Predicted vs actual (test set) — median error {metrics['median_ape']:.1%}")
    ax.legend(markerscale=3)
    fig.savefig(FIGURES_DIR / "08_predicted_vs_actual.png", dpi=120, bbox_inches="tight")

    # Error distribution
    pct_err = (pred - price) / price * 100
    fig, axes = plt.subplots(1, 2, figsize=(14, 5))
    axes[0].hist(np.clip(pct_err, -60, 60), bins=60)
    axes[0].axvline(0, color="k", lw=1)
    axes[0].set(xlabel="Prediction error (%)", ylabel="Listings",
                title="Error distribution (clipped at ±60%)")
    city_err = pd.DataFrame(by_city).T["median_ape"].sort_values() * 100
    axes[1].barh(city_err.index, city_err.values)
    for i, v in enumerate(city_err.values):
        axes[1].text(v, i, f" {v:.1f}%", va="center")
    axes[1].set(xlabel="Median % error", title="Typical error by city")
    fig.savefig(FIGURES_DIR / "09_errors.png", dpi=120, bbox_inches="tight")

    # Grouped permutation importance
    print("\nComputing permutation importance ...")
    imp = grouped_permutation_importance(model, X, y_log)
    groups = sorted([d for d in imp if d["kind"] == "group"], key=lambda d: d["importance"])
    top_amen = sorted([d for d in imp if d["kind"] == "amenity"], key=lambda d: d["importance"])[-10:]
    fig, axes = plt.subplots(1, 2, figsize=(15, 5))
    for ax, rows, title in ((axes[0], groups, "Feature groups"), (axes[1], top_amen, "Top 10 individual amenities")):
        ax.barh([d["feature"] for d in rows], [d["importance"] for d in rows],
                xerr=[d["std"] for d in rows])
        ax.set(xlabel="Drop in R² (log price) when shuffled", title=title)
    fig.suptitle("Permutation importance (test set)")
    fig.savefig(FIGURES_DIR / "10_feature_importance.png", dpi=120, bbox_inches="tight")
    plt.close("all")

    meta["test_metrics"] = metrics
    meta["test_metrics_by_city"] = by_city
    meta["feature_importance"] = sorted(imp, key=lambda d: -d["importance"])
    METADATA_PATH.write_text(json.dumps(meta, indent=2, ensure_ascii=False))
    pd.DataFrame(by_city).T.round(4).to_csv(REPORTS_DIR / "test_metrics_by_city.csv")
    print(f"Figures saved to {FIGURES_DIR}")


if __name__ == "__main__":
    main()
