from pathlib import Path

from app.services.result_preview import ResultPreviewError, result_preview_service


FIXTURE = Path(__file__).resolve().parent.parent / "fixtures" / "phase2c" / "nflverse_week.csv"


def pending_bet(
    *, market="rushing_yards", side="Over", line=55.0, player_name="Saquon Barkley",
    player_key="saquon barkley", team="PHI", opponent="DAL",
):
    return {
        "id": "bet-1",
        "status": "pending",
        "player_name": player_name,
        "market": market,
        "side_label": side,
        "line": line,
        "result_identity": {
            "status": "ready",
            "season": 2025,
            "week": 1,
            "player_key": player_key,
            "team": team,
            "opponent": opponent,
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


def test_preview_anytime_td_suggests_won_only_when_an_offensive_td_is_present(monkeypatch):
    content = FIXTURE.read_text(encoding="utf-8")
    monkeypatch.setattr(result_preview_service, "_season_content", lambda season, refresh: (content, "2025-09-08T12:00:00+00:00", False))

    report = result_preview_service.preview([pending_bet(market="anytime_td", side="Yes", line=0.5)])

    proposal = report["proposals"][0]
    assert proposal["status"] == "proposal"
    assert proposal["proposed_result"] == "won"
    assert proposal["actual_stat"] == 1.0
    assert proposal["stat_label"] == "offensive rushing/receiving TDs"


def test_preview_anytime_td_never_infers_a_loss_from_no_offensive_td(monkeypatch):
    content = FIXTURE.read_text(encoding="utf-8")
    monkeypatch.setattr(result_preview_service, "_season_content", lambda season, refresh: (content, "2025-09-08T12:00:00+00:00", False))

    report = result_preview_service.preview([
        pending_bet(
            market="anytime_td", side="Yes", line=0.5, player_name="CeeDee Lamb",
            player_key="ceedee lamb", team="DAL", opponent="PHI",
        )
    ])

    proposal = report["proposals"][0]
    assert proposal["status"] == "player_review"
    assert "Do not infer a loss" in proposal["message"]


def test_preview_allows_a_fully_identified_manual_standard_prop(monkeypatch):
    content = FIXTURE.read_text(encoding="utf-8")
    monkeypatch.setattr(result_preview_service, "_season_content", lambda season, refresh: (content, "2025-09-08T12:00:00+00:00", False))
    manual = {
        **pending_bet(),
        "entry_origin": "manual",
        "result_identity": {**pending_bet()["result_identity"], "status": "manual_required"},
    }

    report = result_preview_service.preview([manual])

    assert report["sources"][0]["season"] == 2025
    assert report["proposals"][0]["status"] == "proposal"
    assert report["proposals"][0]["proposed_result"] == "won"


def test_preview_keeps_incomplete_manual_bets_on_manual_settlement():
    manual = {
        **pending_bet(opponent=""),
        "entry_origin": "manual",
        "result_identity": {**pending_bet(opponent="")["result_identity"], "status": "manual_required"},
    }

    report = result_preview_service.preview([manual], refresh=False)

    assert report["sources"] == []
    assert report["proposals"][0]["status"] == "manual_required"
    assert "add player, team, opponent, season, and NFL week" in report["proposals"][0]["message"]


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
