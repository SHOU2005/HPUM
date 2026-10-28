"""Exploratory data analysis -> reports/figures/*.png

Run:  python -m src.eda
"""
import json

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns

from src.config import AMENITIES, AMENITY_LABELS, AUDIT_PATH, CITIES, FIGURES_DIR, MISSING_CODE, REPORTS_DIR
from src.data import load_clean, load_raw

sns.set_theme(style="whitegrid", font="DejaVu Sans")  # bundled with matplotlib, has the ₹ glyph
CITY_COLORS = dict(zip(CITIES, sns.color_palette("colorblind", len(CITIES))))


def save(fig, name):
    fig.savefig(FIGURES_DIR / name, dpi=120, bbox_inches="tight")
    plt.close(fig)


def main():
    raw, df = load_raw(), load_clean()
    df["PricePerSqft"] = df["Price"] / df["Area"]
    df["PriceLakh"] = df["Price"] / 1e5

    # 1. Data-quality audit: why the "not recorded" rows were dropped
    raw["Rows"] = np.where((raw[AMENITIES] == MISSING_CODE).all(axis=1),
                           "Amenities not recorded (dropped)", "Amenities recorded (kept)")
    corr = json.loads(AUDIT_PATH.read_text())["price_area_correlation"]
    fig, axes = plt.subplots(1, 2, figsize=(14, 5.5), sharex=True, sharey=True)
    for ax, (label, g), r in zip(axes, raw.groupby("Rows", sort=False),
                                 (corr["amenities_recorded"], corr["amenities_not_recorded"])):
        g = g.sample(min(len(g), 4000), random_state=0)
        ax.scatter(g["Area"], g["Price"] / 1e5, s=4, alpha=0.3)
        ax.set(xscale="log", yscale="log", xlabel="Area (sq ft)", ylabel="Price (₹ lakh)",
               title=f"{label}\ncorrelation (log) = {r:.2f}")
    fig.suptitle("Data-quality audit: price vs area in the raw data")
    save(fig, "01_data_quality_audit.png")

    # 2. Listings per city
    fig, ax = plt.subplots(figsize=(8, 4.5))
    counts = df["City"].value_counts().reindex(CITIES)
    ax.bar(counts.index, counts.values, color=[CITY_COLORS[c] for c in counts.index])
    for i, v in enumerate(counts.values):
        ax.text(i, v, f"{v:,}", ha="center", va="bottom")
    ax.set(title="Clean listings per city", ylabel="Listings")
    save(fig, "02_listings_per_city.png")

    # 3. Price per sq ft by city
    fig, ax = plt.subplots(figsize=(9, 5))
    order = df.groupby("City")["PricePerSqft"].median().sort_values().index
    sns.boxplot(data=df, x="City", y="PricePerSqft", order=order, hue="City", palette=CITY_COLORS,
                legend=False, showfliers=False, ax=ax)
    ax.set(title="Price per sq ft by city (outliers hidden)", ylabel="₹ per sq ft", xlabel="")
    save(fig, "03_price_per_sqft_by_city.png")

    # 4. Price vs area
    fig, ax = plt.subplots(figsize=(9, 6))
    for c in CITIES:
        g = df[df["City"] == c]
        ax.scatter(g["Area"], g["PriceLakh"], s=6, alpha=0.4, label=c, color=CITY_COLORS[c])
    ax.set(xscale="log", yscale="log", xlabel="Area (sq ft)", ylabel="Price (₹ lakh)",
           title="Price vs area (log scales)")
    ax.legend(markerscale=3)
    save(fig, "04_price_vs_area.png")

    # 5. Priciest localities (min 15 listings)
    loc = (df.groupby(["City", "Location"])["PricePerSqft"].agg(["median", "size"])
             .query("size >= 15").sort_values("median").tail(15))
    fig, ax = plt.subplots(figsize=(9, 6))
    labels = [f"{l}, {c}" for c, l in loc.index]
    ax.barh(labels, loc["median"], color=[CITY_COLORS[c] for c, _ in loc.index])
    ax.set(title="15 most expensive localities (median ₹/sq ft, ≥15 listings)", xlabel="₹ per sq ft")
    save(fig, "05_top_localities.png")

    # 6. BHK and new vs resale
    fig, axes = plt.subplots(1, 2, figsize=(14, 5))
    sns.boxplot(data=df[df["BHK"] <= 5], x="BHK", y="PriceLakh", showfliers=False, ax=axes[0], color="#4c72b0")
    axes[0].set(title="Price by BHK", ylabel="Price (₹ lakh)")
    sns.barplot(data=df.assign(Type=df["Resale"].map({0: "New", 1: "Resale"})), x="City", y="PricePerSqft",
                hue="Type", estimator=np.median, errorbar=None, order=CITIES, ax=axes[1])
    axes[1].set(title="Median ₹/sq ft: new vs resale", ylabel="₹ per sq ft", xlabel="")
    save(fig, "06_bhk_and_resale.png")

    # 7. Amenity premium: median ₹/sq ft with vs without (within-city adjusted)
    rel = df["PricePerSqft"] / df.groupby("City")["PricePerSqft"].transform("median")
    prem = pd.Series({AMENITY_LABELS[a]: rel[df[a] == 1].median() / rel[df[a] == 0].median() - 1
                      for a in AMENITIES if 30 <= df[a].sum() <= len(df) - 30}).sort_values()
    fig, ax = plt.subplots(figsize=(9, 8))
    ax.barh(prem.index, prem.values * 100, color=np.where(prem.values >= 0, "#4c72b0", "#c44e52"))
    ax.axvline(0, color="k", lw=0.8)
    ax.set(title="Amenity premium: ₹/sq ft with vs without (city-adjusted)", xlabel="% difference")
    save(fig, "07_amenity_premium.png")

    summary = df.groupby("City").agg(listings=("Price", "size"), localities=("Location", "nunique"),
                                     median_price_lakh=("PriceLakh", "median"),
                                     median_ppsf=("PricePerSqft", "median"),
                                     median_area=("Area", "median")).round(1)
    summary.to_csv(REPORTS_DIR / "city_summary.csv")
    print(summary.to_string())
    print(f"\nFigures saved to {FIGURES_DIR}")


if __name__ == "__main__":
    main()
