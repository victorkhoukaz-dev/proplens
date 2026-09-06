from fastapi.testclient import TestClient
import pytest

from app.api import routes
from app.db.bet_tracker_store import bet_tracker_store
from app.main import app


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(bet_tracker_store, "path", tmp_path / "tracked_bets.json")
    return TestClient(app)


def test_confirmed_preview_saves_exact_stat_source_and_history(client, monkeypatch):
    def preview(_bets, *, refresh):
        assert refresh is False
        return {
            "sources": [{"source": "nflverse", "fetched_at": "2025-09-08T12:00:00+00:00"}],
            "proposals": [
                {
                    "bet_id": _bets[0]["id"],
                    "status": "proposal",
                    "proposed_result": "won",
                    "actual_stat": 60.0,
                    "stat_label": "rushing yards",
                }
            ],
        }

    monkeypatch.setattr(routes.result_preview_service, "preview", preview)
    created = client.post(
        "/api/tracker/bets",
        json={
            "player_name": "Saquon Barkley", "team": "PHI", "opponent": "DAL",
            "market": "rushing_yards", "side_label": "Over", "line": 55.0,
            "decimal_odds": 1.9, "stake": 5, "bet_type": "cash", "projection_mean": 60,
            "model_win_probability": 0.5, "model_fair_decimal": 2.0, "expected_value_pct": 0,
            "result_identity": {"status": "ready", "season": 2025, "week": 1, "player_key": "saquon barkley", "team": "PHI", "opponent": "DAL"},
        },
    ).json()["bet"]

    response = client.post(f"/api/tracker/bets/{created['id']}/confirm-result-preview", json={"expected_result": "won"})

    assert response.status_code == 200
    bet = response.json()["bet"]
    assert bet["status"] == "won"
    assert bet["profit"] == 4.5
    assert bet["settlement_evidence"]["source"] == "nflverse"
    assert bet["settlement_evidence"]["actual_stat"] == 60.0
    assert bet["settlement_history"][-1]["source"] == "result_preview"
    assert client.post(f"/api/tracker/bets/{created['id']}/confirm-result-preview", json={"expected_result": "won"}).status_code == 409


def test_confirm_preview_refuses_when_recheck_is_not_an_exact_match(client, monkeypatch):
    monkeypatch.setattr(routes.result_preview_service, "preview", lambda *_args, **_kwargs: {"sources": [], "proposals": [{"status": "player_review"}]})
    created = client.post(
        "/api/tracker/bets",
        json={
            "player_name": "Saquon Barkley", "team": "PHI", "opponent": "DAL",
            "market": "rushing_yards", "side_label": "Over", "line": 55.0,
            "decimal_odds": 1.9, "stake": 5, "bet_type": "cash", "projection_mean": 60,
            "model_win_probability": 0.5, "model_fair_decimal": 2.0, "expected_value_pct": 0,
        },
    ).json()["bet"]

    response = client.post(f"/api/tracker/bets/{created['id']}/confirm-result-preview", json={"expected_result": "won"})

    assert response.status_code == 409
    assert client.get("/api/tracker/bets").json()["bets"][0]["status"] == "pending"
