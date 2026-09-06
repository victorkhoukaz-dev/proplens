from pathlib import Path

from app.services.result_preview import ResultPreviewError, result_preview_service


FIXTURE = Path(__file__).resolve().parent.parent / "fixtures" / "phase2c" / "nflverse_week.csv"


def pending_bet(*, market="rushing_yards", side="Over", line=55.0, player_key="saquon barkley"):
    return {
        "id": "bet-1",
        "status": "pending",
        "player_name": "Saquon Barkley",
        "market": market,
        "side_label": side,
        "line": line,
        "result_identity": {
            "status": "ready",
            "season": 2025,
            "week": 1,
            "player_key": player_key,
            "team": "PHI",
            "opponent": "DAL",
        },
    }


def test_preview_proposes_result_without_settling_or_network(monkeypatch):
    content = FIXTURE.read_text(encoding="utf-8")
    monkeypatch.setattr(result_preview_service, "_season_content", lambda season, refresh: (content, "2025-09-08T12:00:00+00:00", False))

    report = result_preview_service.preview([pending_bet()])

    assert report["preview_only"] is True
    assert report["checked_pending"] == 1
    assert report["proposals"] == [
        {
            "bet_id": "bet-1",
            "player_name": "Saquon Barkley",
            "market": "rushing_yards",
            "line": 55.0,
            "status": "proposal",
            "proposed_result": "won",
            "actual_stat": 60.0,
            "stat_label": "rushing yards",
            "message": "Preview only — confirm it against Bet365 before recording the result.",
        }
    ]


def test_preview_never_assumes_missing_player_has_zero(monkeypatch):
    content = FIXTURE.read_text(encoding="utf-8")
    monkeypatch.setattr(result_preview_service, "_season_content", lambda season, refresh: (content, "2025-09-08T12:00:00+00:00", False))

    report = result_preview_service.preview([pending_bet(player_key="inactive player")])

    assert report["proposals"][0]["status"] == "player_review"
    assert "missing does not mean zero" in report["proposals"][0]["message"]


def test_preview_leaves_touchdowns_for_manual_review_without_downloading(monkeypatch):
    monkeypatch.setattr(result_preview_service, "_season_content", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("Should not fetch")))

    report = result_preview_service.preview([pending_bet(market="anytime_td", side="Yes", line=0.5)])

    assert report["sources"] == []
    assert report["proposals"][0]["status"] == "unsupported_market"


def test_preview_translates_missing_season_file_into_waiting_for_stats(monkeypatch):
    monkeypatch.setattr(
        result_preview_service,
        "_season_content",
        lambda *args, **kwargs: (_ for _ in ()).throw(ResultPreviewError("nflverse returned HTTP 404.")),
    )

    report = result_preview_service.preview([pending_bet()])

    proposal = report["proposals"][0]
    assert proposal["status"] == "stats_unavailable"
    assert proposal["message"] == "Final nflverse stats are not available for 2025 Week 1 yet. This bet remains pending."
