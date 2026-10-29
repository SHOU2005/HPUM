"""Tests for the price guessing game."""
import random

import pytest
from fastapi.testclient import TestClient

from api import app
from src.game import _split, new_round, score_guess

client = TestClient(app)


def test_round_hides_the_price():
    r = new_round(random.Random(1))
    assert "Price" not in r["listing"]
    assert set(r["listing"]) >= {"city", "locality", "area_sqft", "bhk", "resale", "amenities"}


def test_round_ids_are_valid_test_rows():
    rng = random.Random(7)
    for _ in range(20):
        r = new_round(rng)
        assert 0 <= r["round_id"] < len(_split())


def test_exact_guess_scores_full_marks():
    result = score_guess(0, float(_split().iloc[0]["Price"]))
    assert result["score"] == 100
    assert result["verdict"] == "Spot on"
    assert result["your_error_pct"] == 0


def test_far_guess_scores_zero():
    actual = float(_split().iloc[0]["Price"])
    result = score_guess(0, actual * 3)
    assert result["score"] == 0
    assert result["verdict"] == "Way off"


def test_score_is_bounded_and_reports_actual_and_model():
    result = score_guess(5, 1_000_000)
    assert 0 <= result["score"] <= 100
    assert result["actual"] == round(float(_split().iloc[5]["Price"]))
    assert result["model"] > 0
    assert isinstance(result["beat_model"], bool)


def test_guess_must_be_positive():
    with pytest.raises(ValueError):
        score_guess(0, 0)


def test_api_round_and_guess():
    r = client.get("/api/game/round")
    assert r.status_code == 200
    body = r.json()
    assert "Price" not in body["listing"]
    g = client.post("/api/game/guess", json={"round_id": body["round_id"], "guess": 8_000_000})
    assert g.status_code == 200
    assert {"actual", "model", "score", "verdict"} <= set(g.json())


def test_api_rejects_out_of_range_round():
    g = client.post("/api/game/guess", json={"round_id": 10**9, "guess": 5_000_000})
    assert g.status_code == 422


def test_api_rejects_bad_guess():
    g = client.post("/api/game/guess", json={"round_id": 0, "guess": 5})
    assert g.status_code == 422
