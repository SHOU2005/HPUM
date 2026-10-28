"""Feature engineering and the price-per-sq-ft model wrapper.

Everything here lives inside the saved sklearn pipeline, so the API only needs
to supply the raw inputs (city, locality, area, BHK, resale, amenities).
"""
import numpy as np
import pandas as pd
from sklearn.base import BaseEstimator, RegressorMixin, TransformerMixin, clone
from sklearn.compose import ColumnTransformer
from sklearn.preprocessing import OneHotEncoder, TargetEncoder

from src.config import AMENITIES, CITIES, INPUT_FEATURES, RANDOM_STATE

ENGINEERED = ["LogArea", "AreaPerBHK", "AmenityCount"]
NUMERIC = ["Area", "BHK", "Resale"] + ENGINEERED + AMENITIES


class FeatureBuilder(BaseEstimator, TransformerMixin):
    """Adds engineered columns and a city-qualified locality key."""

    def fit(self, X, y=None):
        return self

    def transform(self, X):
        X = pd.DataFrame(X, columns=INPUT_FEATURES).copy()
        X["LogArea"] = np.log(X["Area"])
        X["AreaPerBHK"] = X["Area"] / X["BHK"]
        X["AmenityCount"] = X[AMENITIES].sum(axis=1)
        # generic names like "Sector 1" exist in several cities, so the key is city-qualified
        X["LocalityKey"] = X["City"] + " | " + X["Location"]
        return X


def encoder():
    """Locality -> cross-fitted target encoding (no leakage); city -> one-hot; numerics pass through."""
    return ColumnTransformer([
        ("locality", TargetEncoder(random_state=RANDOM_STATE), ["LocalityKey"]),
        ("city", OneHotEncoder(categories=[CITIES], handle_unknown="ignore"), ["City"]),
        ("numeric", "passthrough", NUMERIC),
    ])


class PricePerSqftRegressor(BaseEstimator, RegressorMixin):
    """Fits the inner model on log(price per sq ft); predicts log(price).

    y is log(price). Predicting the rate rather than the total mirrors how the Indian
    market quotes prices and lets locality encoding learn each area's ₹/sq ft directly.
    """

    def __init__(self, estimator):
        self.estimator = estimator

    def fit(self, X, y):
        self.estimator_ = clone(self.estimator).fit(X, np.asarray(y) - np.log(X["Area"].to_numpy()))
        return self

    def predict(self, X):
        return self.estimator_.predict(X) + np.log(X["Area"].to_numpy())
