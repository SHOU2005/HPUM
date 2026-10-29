"""Tests for the decision-support features: valuation, what-if, compare and listing parsing."""
import pytest
from fastapi.testclient import TestClient

from api import app
from src.insights import compare, parse_listing, valuate, what_if
from src.predict import predict

client = TestClient(app)
PROP = dict(city="Mumbai", locality="Thane West", area_sqft=1050, bhk=2, resale=True,
            amenities=["LiftAvailable", "CarParking"])


@pytest.fixture(scope="module")
def estimate():
    return predict(PROP["city"], PROP["locality"], PROP["area_sqft"], PROP["bhk"], PROP["resale"],
                   PROP["amenities"])


# ---------------------------------------------------------------- valuation
def test_valuation_bands(estimate):
    assert valuate(estimate, estimate["price"])["verdict"] == "Close to fair value"
    assert valuate(estimate, estimate["low"] * 0.9)["verdict"] == "Below the fair range"
    assert valuate(estimate, estimate["high"] * 1.1)["verdict"] == "Above the fair range"


def test_valuation_gap_sign(estimate):
    assert valuate(estimate, estimate["price"] * 1.2)["gap_pct"] == pytest.approx(20.0, abs=0.1)
    assert valuate(estimate, estimate["price"] * 0.8)["gap_pct"] == pytest.approx(-20.0, abs=0.1)


def test_valuation_rejects_non_positive_price(estimate):
    with pytest.raises(ValueError):
        valuate(estimate, 0)


# ---------------------------------------------------------------- what-if
def test_what_if_base_and_scenarios():
    result = what_if(**PROP)
    assert result["base_price"] == predict(**PROP)["price"]
    ids = {s["id"] for s in result["scenarios"]}
    assert {"area-10", "area+10", "resale"} <= ids
    assert any(i.startswith("add:") for i in ids)


def test_what_if_bigger_area_costs_more():
    result = what_if(**PROP)
    bigger = next(s for s in result["scenarios"] if s["id"] == "area+10")
    assert bigger["price"] > result["base_price"]
    assert bigger["change"]["area_sqft"] == round(PROP["area_sqft"] * 1.1)


def test_what_if_never_suggests_selected_amenity():
    result = what_if(**PROP)
    added = {s["id"].split(":")[1] for s in result["scenarios"] if s["id"].startswith("add:")}
    assert not added & set(PROP["amenities"])


def test_what_if_scenario_change_reproduces_price():
    result = what_if(**PROP)
    for s in result["scenarios"]:
        c = s["change"]
        again = predict(PROP["city"], PROP["locality"], c["area_sqft"], c["bhk"], c["resale"],
                        c["amenities"])["price"]
        assert again == s["price"]


# ---------------------------------------------------------------- compare
def test_compare_ranks_best_value_first():
    other = dict(city="Chennai", locality="Velachery", area_sqft=1200, bhk=3, resale=False, amenities=[])
    rows = compare([PROP, other])
    assert [r["rank"] for r in rows] == [1, 2]
    assert rows[0]["estimate"]["price_per_sqft"] <= rows[1]["estimate"]["price_per_sqft"]


# ---------------------------------------------------------------- listing text
def test_parse_crore_price_and_bhk_and_locality():
    r = parse_listing("Spacious 2 BHK resale flat in Thane West, 1,050 sq ft, asking ₹1.25 Cr.")
    assert r["area_sqft"] == 1050
    assert r["bhk"] == 2
    assert r["asking_price"] == 12_500_000
    assert r["resale"] is True
    assert (r["city"], r["locality"]) == ("Mumbai", "Thane West")


def test_parse_lakh_and_full_indian_number():
    assert parse_listing("Rs 85 lakh | 2BHK | 980 sq.ft")["asking_price"] == 8_500_000
    assert parse_listing("3 BHK new property 1450 sqft Rs. 1,35,00,000")["asking_price"] == 13_500_000


def test_parse_new_property_flag():
    assert parse_listing("ready to move 3 BHK 1200 sq ft ₹90 L")["resale"] is False


def test_parse_ignores_area_and_bhk_as_price():
    r = parse_listing("2 BHK 900 sq ft, call for details")
    assert r["asking_price"] is None
    assert r["area_sqft"] == 900 and r["bhk"] == 2


def test_parse_longest_locality_wins():
    r = parse_listing("Flat in Whitefield Hope Farm Junction, Bangalore, 1100 sq ft, ₹80 L")
    assert r["locality"] == "Whitefield Hope Farm Junction"


def test_parse_rejects_implausible_values():
    r = parse_listing("5 BHK in 40 sq ft for ₹3 Cr")
    assert r["area_sqft"] is None  # 40 sq ft is below the plausible minimum
    assert r["bhk"] == 5


def test_parse_empty_text_returns_nothing_found():
    assert parse_listing("")["found"] == []


# ---------------------------------------------------------------- API
def test_api_valuate():
    r = client.post("/api/valuate", json={"property": PROP, "asking_price": 12_500_000})
    assert r.status_code == 200
    body = r.json()
    assert body["estimate"]["price"] > 0
    assert body["verdict"] in {"Below the fair range", "Within the fair range",
                               "Close to fair value", "Above the fair range"}


def test_api_valuate_rejects_bad_price():
    r = client.post("/api/valuate", json={"property": PROP, "asking_price": 5})
    assert r.status_code == 422


def test_api_what_if():
    r = client.post("/api/what-if", json=PROP)
    assert r.status_code == 200
    assert r.json()["scenarios"]


def test_api_compare_needs_two_properties():
    assert client.post("/api/compare", json={"properties": [PROP]}).status_code == 422
    r = client.post("/api/compare", json={"properties": [PROP, PROP]})
    assert r.status_code == 200 and len(r.json()) == 2


def test_api_parse_listing():
    r = client.post("/api/parse-listing", json={"text": "2 BHK 1050 sq ft Thane West ₹1.2 Cr"})
    assert r.status_code == 200
    assert r.json()["bhk"] == 2
