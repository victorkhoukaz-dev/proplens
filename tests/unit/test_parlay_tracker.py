"""Tests for the Phase 3C local parlay ledger."""
from fastapi.testclient import TestClient

from app.db.bet_tracker_store import bet_tracker_store
from app.db.parlay_tracker_store import parlay_tracker_store
from app.main import app


def payload(**overrides):
    base = {
        "legs": [
            {"player_name": "Saquon Barkley", "team": "PHI", "opponent": "DAL", "market": "rushing_yards", "side_label": "Over", "line": 70, "decimal_odds": 1.9, "probability": 0.52, "result_identity": {"status": "ready", "season": 2025, "week": 1}},
            {"player_name": "CeeDee Lamb", "team": "DAL", "opponent": "PHI", "market": "receiving_yards", "side_label": "Over", "line": 65, "decimal_odds": 1.9, "probability": 0.48, "result_identity": {"status": "ready", "season": 2025, "week": 1}},
        ],
        "original_decimal_odds": 5.0,
        "effective_decimal_odds": 6.0,
        "stake": 4.0,
        "bet_type": "cash",
        "profit_boost_pct": 25.0,
        "actual_total_return": None,
        "independent_model_probability": 0.25,
        "personal_sensitivity_probability": None,
    }
    return {**base, **overrides}


def test_tracked_parlay_retains_legs_and_boosted_win_return(tmp_path, monkeypatch):
    monkeypatch.setattr(parlay_tracker_store, "path", tmp_path / "tracked_parlays.json")
    client = TestClient(app)

    created = client.post("/api/tracker/parlays", json=payload())
    assert created.status_code == 200
    parlay = created.json()["parlay"]
    assert len(parlay["legs"]) == 2
    assert parlay["original_decimal_odds"] == 5.0
    assert parlay["effective_decimal_odds"] == 6.0
    assert parlay["winning_total_return"] == 24.0

    settled = client.post(f"/api/tracker/parlays/{parlay['id']}/settle", json={"status": "won"})
    assert settled.status_code == 200
    assert settled.json()["parlay"]["profit"] == 20.0


def test_bonus_parlay_loss_and_adjusted_cash_payouts(tmp_path, monkeypatch):
    monkeypatch.setattr(parlay_tracker_store, "path", tmp_path / "tracked_parlays.json")
    client = TestClient(app)

    bonus = client.post("/api/tracker/parlays", json=payload(bet_type="bonus")).json()["parlay"]
    lost = client.post(f"/api/tracker/parlays/{bonus['id']}/settle", json={"status": "lost"})
    assert lost.json()["parlay"]["profit"] == 0.0

    cash = client.post("/api/tracker/parlays", json=payload()).json()["parlay"]
    adjusted = client.post(f"/api/tracker/parlays/{cash['id']}/settle", json={"status": "void_adjusted", "settlement_amount": 3.0})
    assert adjusted.status_code == 200
    assert adjusted.json()["parlay"]["profit"] == -1.0


def test_tracked_parlay_can_be_corrected_after_settlement(tmp_path, monkeypatch):
    monkeypatch.setattr(parlay_tracker_store, "path", tmp_path / "tracked_parlays.json")
    client = TestClient(app)
    parlay = client.post("/api/tracker/parlays", json=payload()).json()["parlay"]

    updated = client.put(
        f"/api/tracker/parlays/{parlay['id']}",
        json={
            "bet_type": "cash",
            "stake": 5,
            "original_decimal_odds": 5,
            "effective_decimal_odds": 6,
            "profit_boost_pct": 25,
            "actual_total_return": None,
            "status": "won",
            "settlement_amount": None,
        },
    )
    assert updated.status_code == 200
    assert updated.json()["parlay"]["winning_total_return"] == 30.0
    assert updated.json()["parlay"]["profit"] == 25.0


def test_parlay_requires_two_legs(tmp_path, monkeypatch):
    monkeypatch.setattr(parlay_tracker_store, "path", tmp_path / "tracked_parlays.json")
    client = TestClient(app)
    response = client.post("/api/tracker/parlays", json=payload(legs=[payload()["legs"][0]]))
    assert response.status_code == 422


def test_overall_summary_can_include_or_exclude_parlays(tmp_path, monkeypatch):
    monkeypatch.setattr(bet_tracker_store, "path", tmp_path / "tracked_bets.json")
    monkeypatch.setattr(parlay_tracker_store, "path", tmp_path / "tracked_parlays.json")
    client = TestClient(app)
    straight = bet_tracker_store.create({"stake": 10, "decimal_odds": 2, "bet_type": "cash"})
    bet_tracker_store.settle(straight["id"], "won")
    parlay = client.post("/api/tracker/parlays", json=payload()).json()["parlay"]
    client.post(f"/api/tracker/parlays/{parlay['id']}/settle", json={"status": "won"})

    combined = client.get("/api/tracker/overall-summary?include_parlays=true").json()["summary"]
    straight_only = client.get("/api/tracker/overall-summary?include_parlays=false").json()["summary"]
    assert combined["total_profit"] == 30.0
    assert combined["cash_wagered"] == 14.0
    assert combined["cash_roi_pct"] == 214.29
    assert combined["total_roi_on_cash_risk_pct"] == 214.29
    assert straight_only["total_profit"] == 10.0
    assert straight_only["cash_wagered"] == 10.0
