"""Tests for Phase 1.1 projection snapshot lifecycle."""

import pytest
from fastapi.testclient import TestClient

from app.db.cache import cache
from app.db.bet_tracker_store import bet_tracker_store
from app.db.loaded_data_store import loaded_data_store
from app.db.projection_snapshot_store import projection_snapshot_store
from app.main import app


@pytest.fixture
def isolated_snapshot_store(tmp_path, monkeypatch):
    monkeypatch.setattr(projection_snapshot_store, "path", tmp_path / "projection_snapshots.json")
    monkeypatch.setattr(loaded_data_store, "path", tmp_path / "loaded_data.json")
    monkeypatch.setattr(bet_tracker_store, "path", tmp_path / "tracked_bets.json")
    cache.replace_projections([])
    yield
    cache.replace_projections([])


@pytest.fixture
def client(isolated_snapshot_store):
    return TestClient(app)


def projection_text(rushing_yards: float) -> str:
    return f"Player,Team,Pos,Opp,Rush Yds\nSaquon Barkley,PHI,RB,DAL,{rushing_yards}\n"


def test_pasted_projection_import_creates_active_week_snapshot(client):
    response = client.post(
        "/api/upload/paste",
        json={
            "data_type": "projections",
            "content": projection_text(70.5),
            "season": 2026,
            "week": 2,
            "label": "Friday update",
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["snapshot"]["active"] is True
    assert data["snapshot"]["season"] == 2026
    assert data["snapshot"]["week"] == 2
    assert data["snapshot"]["label"] == "Friday update"

    library = client.get("/api/projection-library").json()
    assert len(library["snapshots"]) == 1
    assert library["snapshots"][0]["matchup_count"] == 1

    players = client.get("/api/evaluator/players?q=saquon").json()
    assert players["projection_context"]["week"] == 2
    assert players["players"][0]["opponent"] == "DAL"
    assert players["players"][0]["projections"]["rushing_yards"] == 70.5


def test_active_snapshot_cannot_be_deleted_and_inactive_snapshot_can(client):
    first = client.post(
        "/api/upload/paste",
        json={"data_type": "projections", "content": projection_text(70.5), "season": 2026, "week": 1},
    ).json()["snapshot"]
    second = client.post(
        "/api/upload/paste",
        json={"data_type": "projections", "content": projection_text(65.5), "season": 2026, "week": 2},
    ).json()["snapshot"]

    active_delete = client.delete(f"/api/projection-library/{second['id']}")
    assert active_delete.status_code == 409

    deleted = client.delete(f"/api/projection-library/{first['id']}")
    assert deleted.status_code == 200

    library = client.get("/api/projection-library").json()
    assert [item["id"] for item in library["snapshots"]] == [second["id"]]


def test_tracker_calculates_bonus_bets_without_a_cash_loss(client):
    payload = {
        "player_name": "Saquon Barkley", "team": "PHI", "opponent": "DAL", "market": "rushing_yards",
        "side_label": "Over", "line": 70.5, "decimal_odds": 2.5, "stake": 10,
        "projection_mean": 70.5, "model_win_probability": 0.5, "model_fair_decimal": 2.0, "expected_value_pct": 5,
    }
    bonus = client.post("/api/tracker/bets", json={**payload, "bet_type": "bonus"}).json()["bet"]
    cash = client.post("/api/tracker/bets", json={**payload, "bet_type": "cash"}).json()["bet"]
    client.post(f"/api/tracker/bets/{bonus['id']}/settle", json={"status": "lost"})
    client.post(f"/api/tracker/bets/{cash['id']}/settle", json={"status": "won"})
    tracker = client.get("/api/tracker/bets").json()
    assert tracker["summary"]["cash_profit"] == 15.0
    assert tracker["summary"]["bonus_profit"] == 0.0
    assert tracker["summary"]["bonus_stake_used"] == 10.0
    assert tracker["summary"]["total_profit"] == 15.0
    assert tracker["summary"]["cash_roi_pct"] == 150.0
    assert tracker["summary"]["total_roi_on_cash_risk_pct"] == 150.0


def test_tracker_separates_cash_bet_roi_from_total_roi_on_cash_risk(client):
    payload = {
        "player_name": "Saquon Barkley", "team": "PHI", "opponent": "DAL", "market": "rushing_yards",
        "side_label": "Over", "line": 70.5, "stake": 5, "projection_mean": 70.5,
        "model_win_probability": 0.5, "model_fair_decimal": 2.0, "expected_value_pct": 5,
    }
    cash = client.post("/api/tracker/bets", json={**payload, "decimal_odds": 2.65, "bet_type": "cash"}).json()["bet"]
    bonus = client.post("/api/tracker/bets", json={**payload, "decimal_odds": 1.60, "bet_type": "bonus"}).json()["bet"]
    client.post(f"/api/tracker/bets/{cash['id']}/settle", json={"status": "won"})
    client.post(f"/api/tracker/bets/{bonus['id']}/settle", json={"status": "won"})

    summary = client.get("/api/tracker/bets").json()["summary"]
    assert summary["cash_profit"] == 8.25
    assert summary["bonus_profit"] == 3.0
    assert summary["total_profit"] == 11.25
    assert summary["cash_wagered"] == 5.0
    assert summary["cash_staked"] == 5.0
    assert summary["bonus_stake_used"] == 5.0
    assert summary["cash_roi_pct"] == 165.0
    assert summary["total_roi_on_cash_risk_pct"] == 225.0


def test_tracker_can_exclude_pending_bets_from_wager_totals(client):
    payload = {
        "player_name": "Saquon Barkley", "team": "PHI", "opponent": "DAL", "market": "rushing_yards",
        "side_label": "Over", "line": 70.5, "decimal_odds": 2.0, "projection_mean": 70.5,
        "model_win_probability": 0.5, "model_fair_decimal": 2.0, "expected_value_pct": 0,
    }
    settled_cash = client.post("/api/tracker/bets", json={**payload, "stake": 5, "bet_type": "cash"}).json()["bet"]
    client.post(f"/api/tracker/bets/{settled_cash['id']}/settle", json={"status": "won"})
    client.post("/api/tracker/bets", json={**payload, "stake": 7, "bet_type": "cash"})
    client.post("/api/tracker/bets", json={**payload, "stake": 3, "bet_type": "bonus"})

    included = client.get("/api/tracker/bets").json()["summary"]
    excluded = client.get("/api/tracker/bets?include_pending=false").json()["summary"]
    assert included["cash_wagered"] == 12.0
    assert included["bonus_stake_used"] == 3.0
    assert excluded["cash_wagered"] == 5.0
    assert excluded["bonus_stake_used"] == 0.0
    assert included["cash_profit"] == excluded["cash_profit"] == 5.0


def test_tracker_supports_cashout_and_corrections_after_settlement(client):
    payload = {
        "player_name": "Saquon Barkley", "team": "PHI", "market": "rushing_yards", "side_label": "Over",
        "line": 70.5, "decimal_odds": 2.0, "stake": 10, "bet_type": "cash", "projection_mean": 70.5,
        "model_win_probability": 0.5, "model_fair_decimal": 2.0, "expected_value_pct": 0,
    }
    bet = client.post("/api/tracker/bets", json=payload).json()["bet"]
    cashed_out = client.post(f"/api/tracker/bets/{bet['id']}/settle", json={"status": "cashed_out", "settlement_amount": 8.25})
    assert cashed_out.status_code == 200
    assert cashed_out.json()["bet"]["profit"] == -1.75
    corrected = client.put(f"/api/tracker/bets/{bet['id']}", json={"stake": 5})
    assert corrected.status_code == 200
    assert corrected.json()["bet"]["profit"] == 3.25


def test_tracker_can_correct_result_and_delete_a_bet(client):
    payload = {
        "player_name": "Saquon Barkley", "team": "PHI", "market": "rushing_yards", "side_label": "Over",
        "line": 70.5, "decimal_odds": 2.0, "stake": 10, "bet_type": "cash", "projection_mean": 70.5,
        "model_win_probability": 0.5, "model_fair_decimal": 2.0, "expected_value_pct": 0,
    }
    bet = client.post("/api/tracker/bets", json=payload).json()["bet"]
    client.post(f"/api/tracker/bets/{bet['id']}/settle", json={"status": "won"})
    corrected = client.put(f"/api/tracker/bets/{bet['id']}", json={"status": "push"})
    assert corrected.status_code == 200
    assert corrected.json()["bet"]["profit"] == 0.0
    deleted = client.delete(f"/api/tracker/bets/{bet['id']}")
    assert deleted.status_code == 200
    assert client.get("/api/tracker/bets").json()["bets"] == []
