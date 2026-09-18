"""Phase 5.0 read-only projection accuracy research tests."""
from datetime import datetime, timezone

from app.db.projection_snapshot_store import ProjectionSnapshot, projection_snapshot_store
from app.schemas.projections import PlayerProjection, StatCategory
from app.services.model_research import model_research_service
from app.services.result_preview import result_preview_service


SCHEDULE = """season,week,game_type,gameday,gametime,home_team,away_team
2026,2,REG,2026-09-13,13:00,PHI,DAL
"""
STATS = """season,week,player_display_name,team,opponent_team,rushing_yards,passing_yards,receiving_yards,receptions,rushing_tds,receiving_tds
2026,2,Saquon Barkley,PHI,DAL,72,0,18,3,1,0
"""


def snapshot(label: str, imported_at: datetime, rushing_yards: float) -> ProjectionSnapshot:
    return ProjectionSnapshot(
        id=label,
        label=label,
        source="FantasyPoints",
        season=2026,
        week=2,
        imported_at=imported_at,
        projections=[
            PlayerProjection(
                player_name="Saquon Barkley",
                team="PHI",
                opponent="DAL",
                position="RB",
                stat_category=StatCategory.RUSHING_YARDS,
                projection_mean=rushing_yards,
                season=2026,
                week=2,
            )
        ],
    )


def test_research_uses_latest_projection_before_kickoff_and_reports_mean_metrics(monkeypatch):
    early = snapshot("Early", datetime(2026, 9, 12, 12, tzinfo=timezone.utc), 65)
    late = snapshot("Late", datetime(2026, 9, 13, 15, tzinfo=timezone.utc), 70)
    post_kickoff = snapshot("Post kickoff", datetime(2026, 9, 14, 2, tzinfo=timezone.utc), 80)
    monkeypatch.setattr(projection_snapshot_store, "list", lambda: [early, late, post_kickoff])
    monkeypatch.setattr(model_research_service, "_schedule_content", lambda refresh: (SCHEDULE, "2026-09-12T00:00:00+00:00", True))
    monkeypatch.setattr(result_preview_service, "_season_content", lambda season, refresh: (STATS, "2026-09-15T00:00:00+00:00", True))

    report = model_research_service.report(season=2026, through_week=2)

    assert report["coverage"] == {
        "supported_imported_rows": 3,
        "selected_pre_kickoff_rows": 1,
        "matched_rows": 1,
        "excluded": {"imported_after_kickoff": 1},
    }
    rushing = report["markets"]
    assert rushing == [{
        "market": "rushing_yards",
        "label": "rushing yards",
        "sample_size": 1,
        "average_projection": 70.0,
        "average_actual": 72.0,
        "bias_actual_minus_projection": 2.0,
        "mae": 2.0,
        "rmse": 2.0,
    }]
    assert report["largest_errors"][0]["snapshot_label"] == "Late"
    detailed = model_research_service.report(season=2026, through_week=2, include_records=True)
    assert len(detailed["records"]) == 1
    assert detailed["records"][0]["snapshot_id"] == "Late"
    assert "records" not in report


def test_research_rejects_import_at_exact_kickoff(monkeypatch):
    at_kickoff = snapshot("Kickoff", datetime(2026, 9, 13, 17, tzinfo=timezone.utc), 65)
    monkeypatch.setattr(projection_snapshot_store, "list", lambda: [at_kickoff])
    monkeypatch.setattr(model_research_service, "_schedule_content", lambda refresh: (SCHEDULE, "test", True))
    report = model_research_service.report(season=2026, through_week=2)
    assert report["coverage"]["selected_pre_kickoff_rows"] == 0
    assert report["coverage"]["excluded"] == {"imported_after_kickoff": 1}


def test_research_excludes_missing_or_ambiguous_final_player_stats(monkeypatch):
    only = snapshot("Only", datetime(2026, 9, 12, 12, tzinfo=timezone.utc), 65)
    monkeypatch.setattr(projection_snapshot_store, "list", lambda: [only])
    monkeypatch.setattr(model_research_service, "_schedule_content", lambda refresh: (SCHEDULE, "2026-09-12T00:00:00+00:00", True))
    monkeypatch.setattr(result_preview_service, "_season_content", lambda season, refresh: (STATS.replace("Saquon Barkley", "Other Player"), "2026-09-15T00:00:00+00:00", True))

    report = model_research_service.report(season=2026, through_week=2)

    assert report["coverage"]["matched_rows"] == 0
    assert report["coverage"]["excluded"] == {"player_stat_missing_or_ambiguous": 1}
    assert report["markets"] == []


def test_research_reports_rushing_attempts_from_nflverse_carries(monkeypatch):
    attempts_snapshot = ProjectionSnapshot(
        id="Attempts",
        label="Attempts",
        source="FantasyPoints",
        season=2026,
        week=2,
        imported_at=datetime(2026, 9, 12, 12, tzinfo=timezone.utc),
        projections=[
            PlayerProjection(
                player_name="Saquon Barkley",
                team="PHI",
                opponent="DAL",
                position="RB",
                stat_category=StatCategory.RUSHING_ATTEMPTS,
                projection_mean=18.2,
                season=2026,
                week=2,
            )
        ],
    )
    stats = STATS.replace("rushing_yards,passing_yards", "rushing_yards,carries,passing_yards").replace("72,0,18", "72,19,0,18")
    monkeypatch.setattr(projection_snapshot_store, "list", lambda: [attempts_snapshot])
    monkeypatch.setattr(model_research_service, "_schedule_content", lambda refresh: (SCHEDULE, "2026-09-12T00:00:00+00:00", True))
    monkeypatch.setattr(result_preview_service, "_season_content", lambda season, refresh: (stats, "2026-09-15T00:00:00+00:00", True))

    report = model_research_service.report(season=2026, through_week=2)

    assert report["markets"][0]["market"] == "rushing_attempts"
    assert report["markets"][0]["average_projection"] == 18.2
    assert report["markets"][0]["average_actual"] == 19.0
