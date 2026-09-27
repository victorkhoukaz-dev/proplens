from app.db.model_research_annotation_store import ModelResearchAnnotationStore


def test_annotation_store_persists_only_review_metadata(tmp_path):
    store = ModelResearchAnnotationStore(tmp_path / "annotations.json")
    record_id = "a" * 24

    saved = store.save(record_id=record_id, classification="verified_in_game_injury", note="Left early")

    assert saved["classification"] == "verified_in_game_injury"
    assert store.get_many([record_id, "b" * 24])[record_id]["note"] == "Left early"
