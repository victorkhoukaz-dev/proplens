"""Local persistence for the odds and projection inputs used by the EV pipeline."""
from __future__ import annotations

import json
import logging
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from pydantic import ValidationError

from app.schemas.odds import Event
from app.schemas.projections import PlayerProjection

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent.parent.parent
DEFAULT_LOADED_DATA_PATH = BASE_DIR / "data" / "loaded_data.json"


def _keep_decimal_odds(value):
    """Store decimal odds as authoritative so a reload cannot alter the price."""
    if isinstance(value, list):
        return [_keep_decimal_odds(item) for item in value]
    if isinstance(value, dict):
        if "american" in value and "decimal" in value:
            return {"decimal": value["decimal"]}
        return {key: _keep_decimal_odds(item) for key, item in value.items()}
    return value


@dataclass(frozen=True)
class LoadedDataSnapshot:
    events: list[Event]
    projections: list[PlayerProjection]


class LoadedDataStore:
    """Atomically save and restore normalized pipeline inputs as JSON."""

    def __init__(self, path: Path = DEFAULT_LOADED_DATA_PATH) -> None:
        self.path = path
        self._lock = threading.RLock()

    def load(self) -> LoadedDataSnapshot | None:
        if not self.path.exists():
            return None

        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(raw, dict) or raw.get("version") != 1:
                raise ValueError("unsupported or missing snapshot version")
            raw_events = raw.get("events", [])
            raw_projections = raw.get("projections", [])
            if not isinstance(raw_events, list) or not isinstance(raw_projections, list):
                raise ValueError("events and projections must be lists")
            events = [Event.model_validate(item) for item in raw_events]
            projections = [PlayerProjection.model_validate(item) for item in raw_projections]
        except (OSError, json.JSONDecodeError, TypeError, ValueError, ValidationError) as exc:
            logger.warning("Could not restore loaded data from %s: %s", self.path, exc)
            return None

        return LoadedDataSnapshot(events=events, projections=projections)

    def save(self, events: list[Event], projections: list[PlayerProjection]) -> None:
        payload = {
            "version": 1,
            "saved_at": datetime.now(timezone.utc).isoformat(),
            "events": [_keep_decimal_odds(event.model_dump(mode="json")) for event in events],
            "projections": [projection.model_dump(mode="json") for projection in projections],
        }
        serialized = json.dumps(payload, indent=2, ensure_ascii=False) + "\n"

        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary_path = self.path.with_suffix(".tmp")
            temporary_path.write_text(serialized, encoding="utf-8")
            temporary_path.replace(self.path)


loaded_data_store = LoadedDataStore()
