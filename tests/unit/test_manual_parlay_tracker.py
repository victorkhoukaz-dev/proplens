"""Phase 4A extension tests for free-text manual parlay tracking."""

import pytest
from fastapi.testclient import TestClient

from app.db.parlay_tracker_store import parlay_tracker_store
from app.main import app


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(parlay_tracker_store, "path", tmp_path / "tracked_parlays.json")
    return TestClient(app)


def payload(**changes):
    base = {
        "description": "Sunday manual parlay",
        "legs": ["T.J. Watt Over 0.5 sacks", "Eagles moneyline"],
        "decimal_odds": 4.0,
        "stake": 5.0,
        "bet_type": "cash",
        "profit_boost_pct": 25.0,
        "actual_total_return": None,
        "season": 2026,
        "week": 1,
        "status": "pending",
    }
    base.update(changes)
    return base


def test_manual_parlay_saves_free_text_legs_and_boosted_return(client):
    response = client.post("/api/tracker/parlays/manual", json=payload())

    assert response.status_code == 200
    parlay = response.json()["parlay"]
    assert parlay["entry_origin"] == "manual"
    assert parlay["description"] == "Sunday manual parlay"
    assert [leg["description"] for leg in parlay["legs"]] == ["T.J. Watt Over 0.5 sacks", "Eagles moneyline"]
    assert parlay["independent_model_probability"] is None
    assert parlay["effective_decimal_odds"] == 4.75
    assert parlay["winning_total_return"] == 23.75
    assert parlay["season"] == 2026
    assert parlay["week"] == 1


def test_manual_parlay_can_be_corrected_and_settled(client):
    parlay = client.post("/api/tracker/parlays/manual", json=payload()).json()["parlay"]
    response = client.put(
        f"/api/tracker/parlays/{parlay['id']}/manual",
        json=payload(
            description="Corrected parlay",
            legs=["T.J. Watt Over 0.5 sacks", "Eagles moneyline", "Over 43.5"],
            decimal_odds=5.0,
            stake=4.0,
            profit_boost_pct=0,
            status="won",
        ),
    )

    assert response.status_code == 200
    corrected = response.json()["parlay"]
    assert len(corrected["legs"]) == 3
    assert corrected["winning_total_return"] == 20.0
    assert corrected["profit"] == 16.0
    assert corrected["status"] == "won"


def test_manual_bonus_parlay_stores_cash_payout_not_non_returned_bonus_value(client):
    response = client.post(
        "/api/tracker/parlays/manual",
        json=payload(decimal_odds=5.0, stake=5.0, bet_type="bonus", profit_boost_pct=0, status="won"),
    )

    assert response.status_code == 200
    parlay = response.json()["parlay"]
    assert parlay["winning_total_return"] == 20.0
    assert parlay["winning_return_includes_stake"] is False
    assert parlay["profit"] == 20.0


def test_manual_parlay_can_mix_guided_and_free_text_legs(client):
    response = client.post(
        "/api/tracker/parlays/manual",
        json=payload(
            legs=[
                {
                    "entry_mode": "structured",
                    "description": "Saquon Barkley · Over · 64.5 · Rushing yards",
                    "category": "player_prop",
                    "player_name": "Saquon Barkley",
                    "position": "RB",
                    "team": "PHI",
                    "opponent": "DAL",
                    "market": "rushing_yards",
                    "side_label": "Over",
                    "line": 64.5,
                },
                {"entry_mode": "free_text", "description": "Eagles moneyline"},
            ]
        ),
    )

    assert response.status_code == 200
    guided, free_text = response.json()["parlay"]["legs"]
    assert guided["entry_mode"] == "structured"
    assert guided["player_name"] == "Saquon Barkley"
    assert guided["market"] == "rushing_yards"
    assert guided["line"] == 64.5
    assert guided["result_identity"]["position"] == "RB"
    assert free_text["entry_mode"] == "free_text"
    assert free_text["market"] == "manual"
    assert free_text["description"] == "Eagles moneyline"


def test_mixed_parlay_retains_evaluated_leg_but_has_no_combined_model_probability(client):
    response = client.post(
        "/api/tracker/parlays/manual",
        json=payload(
            legs=[
                {
                    "entry_mode": "evaluated",
                    "description": "Saquon Barkley · Over · 64.5 · Rushing yards",
                    "category": "player_prop",
                    "player_name": "Saquon Barkley",
                    "position": "RB",
                    "team": "PHI",
                    "opponent": "DAL",
                    "market": "rushing_yards",
                    "side_label": "Over",
                    "line": 64.5,
                    "decimal_odds": 1.9,
                    "probability": 0.54,
                    "result_identity": {"season": 2026, "week": 1, "position": "RB"},
                },
                {"entry_mode": "free_text", "description": "Eagles moneyline"},
            ]
        ),
    )

    assert response.status_code == 200
    parlay = response.json()["parlay"]
    assert parlay["entry_origin"] == "mixed"
    assert parlay["independent_model_probability"] is None
    assert parlay["legs"][0]["entry_mode"] == "evaluated"
    assert parlay["legs"][0]["probability"] == 0.54
    assert parlay["legs"][0]["result_identity"]["season"] == 2026
    assert parlay["legs"][1]["entry_mode"] == "free_text"


def test_manual_parlay_requires_two_legs_and_complete_week_context(client):
    one_leg = client.post("/api/tracker/parlays/manual", json=payload(legs=["Eagles moneyline"]))
    partial_week = client.post("/api/tracker/parlays/manual", json=payload(week=None))

    assert one_leg.status_code == 422
    assert partial_week.status_code == 400
    assert "both season and NFL week" in partial_week.json()["detail"]
