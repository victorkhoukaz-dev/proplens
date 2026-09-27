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


def test_complete_manual_tackles_assists_bet_is_result_preview_eligible(client):
    response = client.post(
        "/api/tracker/bets/manual",
        json=manual_payload(market="tackles_assists", side_label="Over", line=7.5),
    )
    assert response.status_code == 200
    bet = response.json()["bet"]
    assert bet["result_identity"]["status"] == "ready"
    assert bet["projection_mean"] is None
    assert bet["model_win_probability"] is None
    model_refresh = client.post("/api/tracker/bets/evaluation-refreshes/preview")
    assert model_refresh.status_code == 200
    assert model_refresh.json()["checked"] == 0


def test_complete_supported_manual_player_prop_is_preview_eligible(client):
    response = client.post(
        "/api/tracker/bets/manual",
        json=manual_payload(
            player_name="Saquon Barkley",
            position="RB",
            team="PHI",
            opponent="DAL",
            market="rushing_yards",
            side_label="Over",
            line=55.0,
            season=2025,
            week=1,
        ),
    )

    assert response.status_code == 200
    assert response.json()["bet"]["result_identity"]["status"] == "ready"


def test_anytime_td_batch_saves_complete_manual_bets_together(client):
    bets = [
        manual_payload(description=name, player_name=name, market="anytime_td", side_label="Yes", line=0.5,
                       team=team, opponent=opponent, decimal_odds=odds, stake=stake,
                       decision_context={"source": "analyst", "analyst": "Joe Dolan"})
        for name, team, opponent, odds, stake in [
            ("Player One", "PHI", "DAL", 2.15, 5),
            ("Player Two", "DAL", "PHI", 3.4, 6),
        ]
    ]
    batch = {"batch_id": "a0fb09a3-6d51-4954-b944-65069955cfa2", "bets": bets}
    response = client.post("/api/tracker/bets/manual/anytime-td-batch", json=batch)

    assert response.status_code == 200
    assert response.json()["count"] == 2
    saved = bet_tracker_store.list()
    assert len(saved) == 2
    assert {bet["player_name"] for bet in saved} == {"Player One", "Player Two"}
    assert all(bet["entry_origin"] == "manual" and bet["result_identity"]["status"] == "ready" for bet in saved)
    assert all(bet["expected_value_pct"] is None and bet["decision_context"]["analyst"] == "Joe Dolan" for bet in saved)
    repeated = client.post("/api/tracker/bets/manual/anytime-td-batch", json=batch)
    assert repeated.status_code == 200
    assert {bet["id"] for bet in repeated.json()["bets"]} == {bet["id"] for bet in saved}
    assert len(bet_tracker_store.list()) == 2
    changed = client.post("/api/tracker/bets/manual/anytime-td-batch", json={**batch, "bets": [{**bets[0], "stake": 7}, bets[1]]})
    assert changed.status_code == 409
    assert len(bet_tracker_store.list()) == 2


def test_anytime_td_batch_rejects_invalid_row_without_saving_anything(client):
    valid = manual_payload(description="Player One", player_name="Player One", market="anytime_td",
                           side_label="Yes", line=0.5, team="PHI", opponent="DAL")
    invalid = {**valid, "description": "Player Two", "player_name": "Player Two", "opponent": None}
    response = client.post("/api/tracker/bets/manual/anytime-td-batch", json={"batch_id": "bb732b69-dfd6-46e9-8581-42a881dc7bed", "bets": [valid, invalid]})

    assert response.status_code == 400
    assert "Row 2" in response.json()["detail"]
    assert bet_tracker_store.list() == []


def test_anytime_td_batch_never_overwrites_an_unreadable_tracker(client):
    bet_tracker_store.path.write_text("not valid JSON", encoding="utf-8")
    bet = manual_payload(description="Player One", player_name="Player One", market="anytime_td",
                         side_label="Yes", line=0.5, team="PHI", opponent="DAL")
    response = client.post("/api/tracker/bets/manual/anytime-td-batch", json={
        "batch_id": "af389ed3-5dbe-411f-a3ce-7262d2824a68", "bets": [bet],
    })
    assert response.status_code == 409
    assert bet_tracker_store.path.read_text(encoding="utf-8") == "not valid JSON"


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
