"""Prediction service shared by the API and the command line.

Example:
  python -m src.predict --city Mumbai --locality "Thane West" --area 1050 --bhk 2 \
      --resale --amenities LiftAvailable CarParking Gymnasium
"""
import argparse
import json
from functools import lru_cache

import joblib
import numpy as np
import pandas as pd

from src.config import (AMENITIES, AREA_PER_BHK_RANGE, CITIES, INPUT_FEATURES, LOCALITIES_PATH,
                        METADATA_PATH, MODEL_PATH)
from src.data import normalise_location


@lru_cache(maxsize=1)
def load_artifacts():
    return (joblib.load(MODEL_PATH), json.loads(METADATA_PATH.read_text()),
            json.loads(LOCALITIES_PATH.read_text()))


def find_locality(city, name):
    """Case-insensitive match against localities seen in training; None if unseen."""
    key = normalise_location(pd.Series([name]))[0].lower()
    return next((loc for loc in load_artifacts()[2][city] if loc["name"].lower() == key), None)


def predict(city, locality, area_sqft, bhk, resale, amenities=()):
    """Return the estimate, the calibrated 80% range and context, all in ₹."""
    if city not in CITIES:
        raise ValueError(f"city must be one of {CITIES}")
    unknown = set(amenities) - set(AMENITIES)
    if unknown:
        raise ValueError(f"unknown amenities: {sorted(unknown)}")

    model, meta, _ = load_artifacts()
    known = find_locality(city, locality)
    location = known["name"] if known else normalise_location(pd.Series([locality]))[0]
    row = {"City": city, "Location": location, "Area": float(area_sqft), "BHK": int(bhk),
           "Resale": int(bool(resale)), **{a: int(a in amenities) for a in AMENITIES}}
    price = float(np.exp(model.predict(pd.DataFrame([row], columns=INPUT_FEATURES))[0]))
    iv = meta["interval"]

    warnings = []
    if not known:
        warnings.append(f"'{locality}' is not in the {city} training data, so the estimate falls back "
                        "to city-level pricing and is less reliable.")
    elif known["listings"] < 5:
        warnings.append(f"Only {known['listings']} listing(s) from {location} in the training data; "
                        "treat the estimate with caution.")
    lo_a, hi_a = meta["area_range"]
    if not lo_a <= area_sqft <= hi_a:
        warnings.append(f"Area is outside the training range ({lo_a:,.0f}–{hi_a:,.0f} sq ft).")
    if not AREA_PER_BHK_RANGE[0] <= area_sqft / bhk <= AREA_PER_BHK_RANGE[1]:
        warnings.append(f"{area_sqft / bhk:,.0f} sq ft per bedroom is unusual for a {bhk} BHK.")

    return {
        "price": round(price),
        "low": round(price * iv["low_factor"]),
        "high": round(price * iv["high_factor"]),
        "coverage": iv["coverage"],
        "price_per_sqft": round(price / area_sqft),
        "locality": location,
        "locality_known": known is not None,
        "locality_median_ppsf": known["median_ppsf"] if known else None,
        "locality_listings": known["listings"] if known else 0,
        "warnings": warnings,
    }


def format_inr(x):
    """₹ in Indian units: 1 lakh = 1,00,000; 1 crore = 100 lakh."""
    return f"₹{x / 1e7:.2f} Cr" if x >= 1e7 else f"₹{x / 1e5:.1f} L"


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--city", required=True, choices=CITIES)
    p.add_argument("--locality", required=True)
    p.add_argument("--area", type=float, required=True, help="area in sq ft")
    p.add_argument("--bhk", type=int, required=True)
    p.add_argument("--resale", action="store_true", help="resale property (default: new)")
    p.add_argument("--amenities", nargs="*", default=[], choices=AMENITIES, metavar="AMENITY")
    a = p.parse_args()
    r = predict(a.city, a.locality, a.area, a.bhk, a.resale, a.amenities)
    print(f"Estimated price : {format_inr(r['price'])}  (₹{r['price_per_sqft']:,}/sq ft)")
    print(f"80% likely range: {format_inr(r['low'])} – {format_inr(r['high'])}")
    if r["locality_median_ppsf"]:
        n = r["locality_listings"]
        print(f"{r['locality']} median: ₹{r['locality_median_ppsf']:,}/sq ft over {n} listing{'s' * (n != 1)}")
    for w in r["warnings"]:
        print("Warning:", w)


if __name__ == "__main__":
    main()
