from pathlib import Path

from app.db.projection_snapshot_store import ProjectionSnapshotStore
from app.schemas.projections import PlayerProjection, StatCategory


def test_snapshot_store_reuses_parsed_history_for_summary_and_get(tmp_path, monkeypatch):
    """Normal evaluator requests must not reread archived projection rows."""
    store = ProjectionSnapshotStore(tmp_path / "projection_snapshots.json")
    snapshot = store.create(
        [
            PlayerProjection(
                player_name="Test Runner",
                team="TST",
                position="RB",
                opponent="OPP",
                stat_category=StatCategory.RUSHING_YARDS,
                projection_mean=64.5,
            )
        ],
        label="Week 2",
        source="Test",
        season=2026,
        week=2,
    )

    original_read_text = Path.read_text

    def fail_if_snapshot_history_is_reread(path, *args, **kwargs):
        if path == store.path:
            raise AssertionError("unchanged snapshot history should use the in-memory cache")
        return original_read_text(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", fail_if_snapshot_history_is_reread)

    summary = store.list_summaries()
    loaded = store.get(snapshot.id)

    assert summary["active_id"] == snapshot.id
    assert summary["snapshots"][0]["projection_count"] == 1
    assert loaded.projections[0].player_name == "Test Runner"
