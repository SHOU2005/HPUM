"""Price guessing game: guess the price of a held-out listing, then compare with the model.

Rounds come from the saved test split, which the model never trained on, so the model's
estimate is an honest benchmark for the player.
"""
import random
from functools import lru_cache

import pandas as pd

from src.config import AMENITIES, AMENITY_LABELS, SPLIT_PATH
from src.predict import predict

MAX_ERROR = 0.5  # a guess 50% or more away from the true price scores 0


@lru_cache(maxsize=1)
def _split():
    df = pd.read_csv(SPLIT_PATH)
    return df.reset_index(drop=True)


def _listing(row):
    amenities = [a for a in AMENITIES if int(row[a]) == 1]
    return {"city": row["City"], "locality": row["Location"], "area_sqft": float(row["Area"]),
            "bhk": int(row["BHK"]), "resale": bool(row["Resale"]), "amenities": amenities,
            "amenity_labels": [AMENITY_LABELS[a] for a in amenities]}


def new_round(rng=None):
    """A random held-out listing. The price is withheld until the player guesses."""
    rng = rng or random.Random()
    df = _split()
    idx = rng.randrange(len(df))
    return {"round_id": idx, "listing": _listing(df.iloc[idx])}


def score_guess(round_id, guess):
    """Score a guess against the true price and the model's estimate for the same listing."""
    if guess <= 0:
        raise ValueError("guess must be positive")
    row = _split().iloc[round_id]
    actual = float(row["Price"])
    listing = _listing(row)
    model_price = predict(listing["city"], listing["locality"], listing["area_sqft"], listing["bhk"],
                          listing["resale"], listing["amenities"])["price"]

    your_error = abs(guess - actual) / actual
    model_error = abs(model_price - actual) / actual
    score = round(100 * max(0.0, 1 - your_error / MAX_ERROR))
    if your_error < 0.05:
        verdict = "Spot on"
    elif your_error < 0.10:
        verdict = "Very close"
    elif your_error < 0.25:
        verdict = "Not bad"
    else:
        verdict = "Way off"
    return {"actual": round(actual), "guess": round(guess), "model": model_price,
            "your_error_pct": round(your_error * 100, 1), "model_error_pct": round(model_error * 100, 1),
            "score": score, "verdict": verdict, "beat_model": your_error < model_error}
