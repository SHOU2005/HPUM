"""Cleaning rules and the price-per-sq-ft wrapper."""
import numpy as np
import pandas as pd
from sklearn.linear_model import LinearRegression

from src.config import AMENITIES, AREA_PER_BHK_RANGE, CITIES, PPSF_RANGE
from src.data import clean, load_raw
from src.features import PricePerSqftRegressor


def test_clean_applies_every_rule():
    df, audit = clean(load_raw())
    assert set(df["City"]) == set(CITIES)
    assert not (df[AMENITIES] == 9).any().any(), "rows with unrecorded amenities must be dropped"
    assert not df.duplicated().any()
    assert (df["Price"] / df["Area"]).between(*PPSF_RANGE).all()
    assert (df["Area"] / df["BHK"]).between(*AREA_PER_BHK_RANGE).all()
    assert audit["final_rows"] == len(df)
    # the corruption finding that justifies dropping rows
    assert audit["price_area_correlation"]["amenities_recorded"] > 0.6
    assert audit["price_area_correlation"]["amenities_not_recorded"] < 0.4


def test_price_per_sqft_wrapper_round_trips():
    # price = 5,000 ₹/sq ft × area exactly -> the wrapper must recover it
    X = pd.DataFrame({"Area": [500.0, 1000.0, 2000.0], "x": [1.0, 2.0, 3.0]})
    y = np.log(5000 * X["Area"])
    model = PricePerSqftRegressor(LinearRegression()).fit(X, y)
    np.testing.assert_allclose(np.exp(model.predict(X)), 5000 * X["Area"], rtol=1e-9)
