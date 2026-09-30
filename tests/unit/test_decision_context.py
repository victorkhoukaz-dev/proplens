"""Placement rationale is optional, except for an evaluated negative-EV wager."""

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.api.routes import DecisionContext, _validated_decision_context
from app.db.bet_tracker_store import bet_tracker_store
from app.main import app


def test_negative_ev_requires_a_reason():
    with pytest.raises(HTTPException, match="negative-EV"):
        _validated_decision_context(None, requires_negative_ev_reason=True)
    with pytest.raises(HTTPException, match="short reason"):
        _validated_decision_context(
            DecisionContext(source="hedge"), requires_negative_ev_reason=True
        )


def test_analyst_context_is_saved_for_a_negative_ev_bet():
    context = _validated_decision_context(
        DecisionContext(source="analyst", analyst="Chris Wecht"),
        requires_negative_ev_reason=True,
    )
    assert context == {"source": "analyst", "analyst": "Chris Wecht"}


def test_positive_ev_context_remains_optional():
    assert _validated_decision_context(None) is None


def test_evaluated_bet_context_can_be_corrected_without_changing_model_snapshot(tmp_path, monkeypatch):
    monkeypatch.setattr(bet_tracker_store, "path", tmp_path / "tracked_bets.json")
    client = TestClient(app)
    created = client.post("/api/tracker/bets", json={
        "player_name": "Saquon Barkley", "team": "PHI", "opponent": "DAL",
        "market": "rushing_yards", "side_label": "Over", "line": 70.5,
        "decimal_odds": 1.86, "stake": 5, "bet_type": "cash",
        "projection_mean": 75, "model_win_probability": 0.55,
        "model_fair_decimal": 1.82, "expected_value_pct": 2.3,
    })
    assert created.status_code == 200
    bet = created.json()["bet"]
    assert bet["decision_context"] is None

    updated = client.put(f"/api/tracker/bets/{bet['id']}", json={
        "decision_context": {"source": "analyst", "analyst": "  Joe Dolan  ", "note": "  matchup note  "},
    })
    assert updated.status_code == 200
    corrected = updated.json()["bet"]
    assert corrected["decision_context"] == {"source": "analyst", "analyst": "Joe Dolan", "note": "matchup note"}
    assert corrected["projection_mean"] == bet["projection_mean"]
    assert corrected["model_win_probability"] == bet["model_win_probability"]

    invalid = client.put(f"/api/tracker/bets/{bet['id']}", json={
        "decision_context": {"source": "analyst"},
    })
    assert invalid.status_code == 422
    assert bet_tracker_store.list()[0]["decision_context"] == corrected["decision_context"]


def test_negative_ev_edit_cannot_replace_reason_with_model_only(tmp_path, monkeypatch):
    monkeypatch.setattr(bet_tracker_store, "path", tmp_path / "tracked_bets.json")
    client = TestClient(app)
    created = client.post("/api/tracker/bets", json={
        "player_name": "Saquon Barkley", "team": "PHI", "opponent": "DAL",
        "market": "rushing_yards", "side_label": "Over", "line": 90.5,
        "decimal_odds": 1.86, "stake": 5, "bet_type": "cash",
        "projection_mean": 75, "model_win_probability": 0.4,
        "model_fair_decimal": 2.5, "expected_value_pct": -25.6,
        "decision_context": {"source": "analyst", "analyst": "Joe Dolan"},
    })
    assert created.status_code == 200
    bet = created.json()["bet"]
    response = client.put(f"/api/tracker/bets/{bet['id']}", json={"decision_context": {"source": "model"}})
    assert response.status_code == 422
    assert bet_tracker_store.list()[0]["decision_context"] == bet["decision_context"]
