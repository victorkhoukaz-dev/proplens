from pathlib import Path

from app.adapters.csv_odds_adapter import CSVOddsAdapter
from app.adapters.fantasypoints import FantasyPointsAdapter
from app.db.loaded_data_store import LoadedDataStore


ROOT = Path(__file__).resolve().parent.parent.parent


def test_loaded_inputs_round_trip(tmp_path):
    events = CSVOddsAdapter().parse_payload(
        (ROOT / "sample_data" / "odds_snapshot_sample.json").read_text(encoding="utf-8")
    )
    projections = FantasyPointsAdapter().parse_projections(
        (ROOT / "sample_data" / "fantasypoints_sample.csv").read_text(encoding="utf-8")
    )
    store = LoadedDataStore(tmp_path / "loaded_data.json")

    store.save(events, projections)
    restored = store.load()

    assert restored is not None
    assert len(restored.events) == len(events)
    assert len(restored.projections) == len(projections)
    assert restored.events[0].model_dump(mode="json") == events[0].model_dump(mode="json")
    assert restored.projections[0].model_dump(mode="json") == projections[0].model_dump(mode="json")


def test_corrupt_loaded_data_falls_back_safely(tmp_path):
    path = tmp_path / "loaded_data.json"
    path.write_text("not valid json", encoding="utf-8")

    assert LoadedDataStore(path).load() is None
