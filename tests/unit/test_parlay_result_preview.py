from pathlib import Path

from fastapi.testclient import TestClient

from app.db.parlay_tracker_store import parlay_tracker_store
from app.db.bet_tracker_store import bet_tracker_store
from app.main import app
from app.services.result_preview import result_preview_service


FIXTURE = Path(__file__).resolve().parent.parent / "fixtures" / "phase2c" / "nflverse_week.csv"


def parlay(*, ceedee_line=115.0, include_free_text=False):
    legs = [
        {
            "entry_mode": "evaluated", "description": "Saquon Barkley Over 55 rushing yards",
            "category": "player_prop", "player_name": "Saquon Barkley", "team": "PHI", "opponent": "DAL",
            "market": "rushing_yards", "side_label": "Over", "line": 55.0,
            "result_identity": {"status": "ready", "season": 2025, "week": 1, "player_key": "saquon barkley", "team": "PHI", "opponent": "DAL"},
        },
        {
            "entry_mode": "evaluated", "description": "CeeDee Lamb Over receiving yards",
            "category": "player_prop", "player_name": "CeeDee Lamb", "team": "DAL", "opponent": "PHI",
            "market": "receiving_yards", "side_label": "Over", "line": ceedee_line,
            "result_identity": {"status": "ready", "season": 2025, "week": 1, "player_key": "ceedee lamb", "team": "DAL", "opponent": "PHI"},
        },
    ]
    if include_free_text:
        legs[1] = {"entry_mode": "free_text", "description": "Eagles moneyline", "market": "manual"}
    return {
        "id": "parlay-1", "status": "pending", "description": "Sunday parlay", "legs": legs,
        "season": 2025, "week": 1,
    }


def test_parlay_preview_groups_final_leg_results_into_a_lost_preview(monkeypatch):
    from app.services.parlay_result_preview import parlay_result_preview_service

    content = FIXTURE.read_text(encoding="utf-8")
    monkeypatch.setattr(result_preview_service, "_season_content", lambda season, refresh: (content, "2025-09-08T12:00:00+00:00", False))

    report = parlay_result_preview_service.preview([parlay()])

    preview = report["parlays"][0]
    assert report["preview_only"] is True
    assert preview["status"] == "proposal"
    assert preview["proposed_result"] == "lost"
    assert [leg["proposed_result"] for leg in preview["legs"]] == ["won", "lost"]


def test_parlay_preview_waits_for_all_legs_and_keeps_free_text_manual(monkeypatch):
    from app.services.parlay_result_preview import parlay_result_preview_service

    content = FIXTURE.read_text(encoding="utf-8")
    monkeypatch.setattr(result_preview_service, "_season_content", lambda season, refresh: (content, "2025-09-08T12:00:00+00:00", False))

    report = parlay_result_preview_service.preview([parlay(include_free_text=True)])

    preview = report["parlays"][0]
    assert preview["status"] == "needs_review"
    assert preview["proposed_result"] is None
    assert preview["legs"][1]["status"] == "manual_required"
    assert "free-text" in preview["legs"][1]["message"]


def test_parlay_preview_suggests_lost_when_a_supported_leg_lost_even_if_another_leg_is_manual(monkeypatch):
    from app.services.parlay_result_preview import parlay_result_preview_service

    content = FIXTURE.read_text(encoding="utf-8")
    monkeypatch.setattr(result_preview_service, "_season_content", lambda season, refresh: (content, "2025-09-08T12:00:00+00:00", False))

    data = parlay(include_free_text=True)
    data["legs"][0]["line"] = 100.0

    report = parlay_result_preview_service.preview([data])

    preview = report["parlays"][0]
    assert preview["status"] == "proposal"
    assert preview["proposed_result"] == "lost"
    assert preview["legs"][1]["status"] == "manual_required"


def test_parlay_preview_requires_manual_bet365_review_for_a_push(monkeypatch):
    from app.services.parlay_result_preview import parlay_result_preview_service

    content = FIXTURE.read_text(encoding="utf-8")
    monkeypatch.setattr(result_preview_service, "_season_content", lambda season, refresh: (content, "2025-09-08T12:00:00+00:00", False))
    data = parlay(ceedee_line=100.0)
    data["legs"][0]["line"] = 60.0

    report = parlay_result_preview_service.preview([data])

    preview = report["parlays"][0]
    assert preview["status"] == "push_review"
    assert preview["proposed_result"] is None


def test_parlay_preview_route_does_not_settle_any_parlay(tmp_path, monkeypatch):
    monkeypatch.setattr(parlay_tracker_store, "path", tmp_path / "tracked_parlays.json")
    content = FIXTURE.read_text(encoding="utf-8")
    monkeypatch.setattr(result_preview_service, "_season_content", lambda season, refresh: (content, "2025-09-08T12:00:00+00:00", False))
    saved = parlay_tracker_store.create({**parlay(), "original_decimal_odds": 3.0, "effective_decimal_odds": 3.0, "stake": 5.0, "bet_type": "cash", "profit_boost_pct": 0, "actual_total_return": None, "winning_total_return": 15.0, "entry_origin": "parlay_evaluator"})
    client = TestClient(app)

    response = client.post("/api/tracker/parlays/results/preview")

    assert response.status_code == 200
    assert response.json()["parlays"][0]["parlay_id"] == saved["id"]
    assert parlay_tracker_store.list()[0]["status"] == "pending"


def test_combined_preview_checks_straights_and_parlays_without_duplicate_refresh(tmp_path, monkeypatch):
    monkeypatch.setattr(parlay_tracker_store, "path", tmp_path / "tracked_parlays.json")
    monkeypatch.setattr(bet_tracker_store, "path", tmp_path / "tracked_bets.json")
    content = FIXTURE.read_text(encoding="utf-8")
    refreshes = []

    def season_content(season, refresh):
        refreshes.append((season, refresh))
        return content, "2025-09-08T12:00:00+00:00", not refresh

    monkeypatch.setattr(result_preview_service, "_season_content", season_content)
    bet_tracker_store.create({
        "player_name": "Saquon Barkley", "market": "rushing_yards", "side_label": "Over", "line": 55.0,
        "stake": 5.0, "bet_type": "cash", "decimal_odds": 1.9,
        "result_identity": {"status": "ready", "season": 2025, "week": 1, "player_key": "saquon barkley", "team": "PHI", "opponent": "DAL"},
    })
    parlay_tracker_store.create({**parlay(), "original_decimal_odds": 3.0, "effective_decimal_odds": 3.0, "stake": 5.0, "bet_type": "cash", "profit_boost_pct": 0, "actual_total_return": None, "winning_total_return": 15.0, "entry_origin": "parlay_evaluator"})

    response = TestClient(app).post("/api/tracker/results/preview/all")

    assert response.status_code == 200
    assert response.json()["checked_straight"] == 1
    assert response.json()["checked_parlays"] == 1
    assert len(response.json()["parlays"]) == 1
    assert refreshes == [(2025, True), (2025, False)]


def test_confirm_parlay_preview_rechecks_then_saves_evidence(tmp_path, monkeypatch):
    monkeypatch.setattr(parlay_tracker_store, "path", tmp_path / "tracked_parlays.json")
    content = FIXTURE.read_text(encoding="utf-8")
    monkeypatch.setattr(result_preview_service, "_season_content", lambda season, refresh: (content, "2025-09-08T12:00:00+00:00", not refresh))
    saved = parlay_tracker_store.create({**parlay(), "original_decimal_odds": 3.0, "effective_decimal_odds": 3.0, "stake": 5.0, "bet_type": "cash", "profit_boost_pct": 0, "actual_total_return": None, "winning_total_return": 15.0, "entry_origin": "parlay_evaluator"})

    response = TestClient(app).post(f"/api/tracker/parlays/{saved['id']}/confirm-result-preview", json={"expected_result": "lost"})

    assert response.status_code == 200
    confirmed = response.json()["parlay"]
    assert confirmed["status"] == "lost"
    assert confirmed["settlement_evidence"]["source"] == "nflverse"
    assert confirmed["settlement_evidence"]["legs"][1]["proposed_result"] == "lost"
