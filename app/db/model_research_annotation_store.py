"""Local, manual annotations for Phase 5 research rows.

Annotations never edit a saved projection, final statistic, wager, or model
evaluation. They only make the research comparison more transparent.
"""
from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


BASE_DIR = Path(__file__).resolve().parent.parent.parent
DEFAULT_ANNOTATION_PATH = BASE_DIR / "data" / "model_research_annotations.json"

VALID_CLASSIFICATIONS = {
    "unreviewed",
    "verified_in_game_injury",
    "non_injury_early_exit",
    "pre_game_inactive_or_scratch",
    "no_special_circumstance",
}


class ModelResearchAnnotationStore:
    """Persist human-reviewed availability context without mutating research data."""

    def __init__(self, path: Path = DEFAULT_ANNOTATION_PATH) -> None:
        self.path = path
        self._lock = threading.RLock()

    def _read(self) -> dict[str, dict[str, Any]]:
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        annotations = payload.get("annotations") if isinstance(payload, dict) else None
        if not isinstance(annotations, dict):
            return {}
        return {str(key): value for key, value in annotations.items() if isinstance(value, dict)}

    def get_many(self, record_ids: list[str]) -> dict[str, dict[str, Any]]:
        with self._lock:
            annotations = self._read()
            return {record_id: dict(annotations[record_id]) for record_id in record_ids if record_id in annotations}

    def save(self, *, record_id: str, classification: str, note: str = "") -> dict[str, Any]:
        if classification not in VALID_CLASSIFICATIONS:
            raise ValueError("Unsupported availability classification.")
        cleaned_note = note.strip()[:500]
        record = {
            "classification": classification,
            "note": cleaned_note,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        with self._lock:
            annotations = self._read()
            annotations[record_id] = record
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.path.with_suffix(".tmp")
            temporary.write_text(
                json.dumps({"version": 1, "annotations": annotations}, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            temporary.replace(self.path)
        return dict(record)


model_research_annotation_store = ModelResearchAnnotationStore()
