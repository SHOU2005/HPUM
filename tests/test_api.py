"""End-to-end checks of the trained model through the REST API."""
import pytest
from fastapi.testclient import TestClient

from api import app
from src.config import MODEL_PATH

pytestmark = pytest.mark.skipif(not MODEL_PATH.exists(), reason="model not trained")
client = TestClient(app)
FLAT = {"city": "Mumbai", "locality": "Thane West", "area_sqft": 1050, "bhk": 2, "resale": True,
        "amenities": ["LiftAvailable", "CarParking"]}


def post(**overrides):
    return client.post("/api/predict", json={**FLAT, **overrides})


def test_health_and_options():
    assert client.get("/api/health").json()["model_loaded"] is True
    opts = client.get("/api/options").json()
    assert "Mumbai" in opts["cities"] and opts["localities"]["Mumbai"]


def test_prediction_is_sane():
    r = post().json()
    assert r["low"] < r["price"] < r["high"]
    assert r["locality_known"] and r["warnings"] == []
    # Thane West 2 BHK: tens of lakhs to low crores, rate within 2x of the locality median
    assert 30e5 < r["price"] < 3e7
    assert 0.5 < r["price_per_sqft"] / r["locality_median_ppsf"] < 2


def test_bigger_flat_costs_more():
    assert post(area_sqft=1600, bhk=3).json()["price"] > post().json()["price"]


def test_city_matters():
    # same flat: Mumbai should cost more than Hyderabad (city median ₹/sq ft ~9.6k vs ~5.1k)
    hyd = post(city="Hyderabad", locality="Gachibowli").json()["price"]
    assert post().json()["price"] > hyd


def test_locality_lookup_is_case_insensitive():
    assert post(locality="  thane   west ").json()["locality"] == "Thane West"


def test_unknown_locality_warns():
    r = post(locality="Atlantis Nagar").json()
    assert not r["locality_known"] and r["warnings"]


@pytest.mark.parametrize("bad", [
    {"city": "Kolkata"}, {"area_sqft": 50}, {"bhk": 0}, {"amenities": ["Helipad"]}, {"locality": ""},
])
def test_invalid_input_rejected(bad):
    assert post(**bad).status_code == 422


def test_frontend_served():
    r = client.get("/")
    assert r.status_code == 200 and "HomeValue" in r.text
    assert client.get("/static/app.js").status_code == 200
