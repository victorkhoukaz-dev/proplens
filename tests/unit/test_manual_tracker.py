"""Phase 4A manual-entry tests using an isolated tracker file."""

import pytest
from fastapi.testclient import TestClient

from app.db.bet_tracker_store import bet_tracker_store
from app.main import app
from app.services.result_preview import result_preview_service


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(bet_tracker_store, "path", tmp_path / "tracked_bets.json")
    return TestClient(app)


def manual_payload(**changes):
    payload = {
        "category": "player_prop",
        "description": "T.J. Watt Over 0.5 Sacks",
        "player_name": "T.J. Watt",
        "position": "LB",
        "team": "PIT",
        "opponent": "BAL",
        "market": "sacks",
        "side_label": "Over",
        "line": 0.5,
        "decimal_odds": 1.85,
        "stake": 10,
        "bet_type": "cash",
        "season": 2026,
        "week": 1,
        "status": "pending",
    }
    payload.update(changes)
    return payload


def test_manual_player_prop_is_saved_without_model_evidence(client):
    response = client.post("/api/tracker/bets/manual", json=manual_payload())

    assert response.status_code == 200
    bet = response.json()["bet"]
    assert bet["entry_origin"] == "manual"
    assert bet["category"] == "player_prop"
    assert bet["projection_mean"] is None
    assert bet["model_win_probability"] is None
    assert bet["model_fair_decimal"] is None
    assert bet["expected_value_pct"] is None
    assert bet["result_identity"]["status"] == "manual_required"
    assert bet["result_identity"]["season"] == 2026
    assert bet["result_identity"]["week"] == 1

    preview = result_preview_service.preview([bet], refresh=False)
    assert preview["sources"] == []
    assert preview["proposals"][0]["status"] == "manual_required"


def test_manual_game_bet_uses_existing_roi_and_settlement_rules(client):
    created = client.post(
        "/api/tracker/bets/manual",
        json=manual_payload(
            category="game_bet",
            description="Philadelphia -3.5",
            player_name=None,
            position=None,
            market="spread",
            side_label="Home",
            line=-3.5,
            decimal_odds=2.0,
            stake=5,
        ),
    ).json()["bet"]

    settled = client.post(f"/api/tracker/bets/{created['id']}/settle", json={"status": "won"})
    assert settled.status_code == 200
    assert settled.json()["bet"]["profit"] == 5.0
    summary = client.get("/api/tracker/bets").json()["summary"]
    assert summary["cash_profit"] == 5.0
    assert summary["cash_wagered"] == 5.0


def test_manual_entry_can_be_fully_corrected(client):
    created = client.post("/api/tracker/bets/manual", json=manual_payload()).json()["bet"]
    corrected_payload = manual_payload(
        description="T.J. Watt Under 1.5 Sacks",
        side_label="Under",
        line=1.5,
        decimal_odds=2.1,
        stake=6,
        status="lost",
    )

    response = client.put(f"/api/tracker/bets/{created['id']}/manual", json=corrected_payload)

    assert response.status_code == 200
    bet = response.json()["bet"]
    assert bet["description"] == "T.J. Watt Under 1.5 Sacks"
    assert bet["line"] == 1.5
    assert bet["status"] == "lost"
    assert bet["profit"] == -6.0
    assert bet["entry_origin"] == "manual"


def test_manual_entry_rejects_partial_week_and_missing_player(client):
    partial_week = client.post("/api/tracker/bets/manual", json=manual_payload(week=None))
    no_player = client.post("/api/tracker/bets/manual", json=manual_payload(player_name=None))

    assert partial_week.status_code == 400
    assert "both season and NFL week" in partial_week.json()["detail"]
    assert no_player.status_code == 400
    assert "player name" in no_player.json()["detail"]
