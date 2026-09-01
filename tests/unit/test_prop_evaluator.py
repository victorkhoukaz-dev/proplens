"""Focused tests for the manual projection-backed prop evaluator."""

import pytest
from fastapi.testclient import TestClient

from app.db.cache import cache
from app.main import app
from app.schemas.projections import PlayerProjection, StatCategory


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture(autouse=True)
def evaluator_projections():
    cache.replace_projections(
        [
            PlayerProjection(
                player_name="Josh Allen",
                canonical_name="Josh Allen",
                team="BUF",
                opponent="KC",
                position="QB",
                stat_category=StatCategory.PASSING_YARDS,
                projection_mean=265.0,
            ),
            PlayerProjection(
                player_name="Travis Kelce",
                canonical_name="Travis Kelce",
                team="KC",
                opponent="BUF",
                position="TE",
                stat_category=StatCategory.ANYTIME_TD,
                projection_mean=0.55,
            ),
        ]
    )
    yield
    cache.replace_projections([])


def test_evaluator_lists_projection_backed_players(client):
    response = client.get("/api/evaluator/players?q=allen")
    assert response.status_code == 200
    player = response.json()["players"][0]
    assert player["player_name"] == "Josh Allen"
    assert player["markets"] == ["passing_yards"]


def test_evaluator_returns_model_only_result_without_market_signal(client):
    response = client.post(
        "/api/evaluator/evaluate",
        json={
            "player_name": "Josh Allen",
            "stat_category": "passing_yards",
            "side": "over",
            "line": 240.5,
            "odds": "-110",
            "stake": 20,
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["evidence"]["code"] == "model_only"
    assert data["evidence"]["label"] in {"Model Edge", "Model Estimate"}
    assert data["prop"]["bet365_american"] == -110
    assert data["model"]["win_probability"] > 0
    assert data["value"]["entered_stake"] == 20
    assert data["value"]["entered_stake_expected_profit"] is not None
    assert "sharp-book" in data["warnings"][1].lower()


def test_evaluator_requires_matching_projection(client):
    response = client.post(
        "/api/evaluator/evaluate",
        json={
            "player_name": "Josh Allen",
            "stat_category": "rushing_yards",
            "side": "over",
            "line": 35.5,
            "odds": -110,
        },
    )
    assert response.status_code == 404
    assert "No matching projection" in response.json()["detail"]


def test_anytime_touchdown_requires_yes_selection(client):
    response = client.post(
        "/api/evaluator/evaluate",
        json={
            "player_name": "Travis Kelce",
            "stat_category": "anytime_td",
            "side": "over",
            "line": 0.5,
            "odds": "+120",
        },
    )
    assert response.status_code == 400
    assert "Yes price" in response.json()["detail"]
