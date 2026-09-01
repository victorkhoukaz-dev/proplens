"""Small, dependency-free local persistence for application settings."""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent.parent.parent
DEFAULT_SETTINGS_PATH = BASE_DIR / "data" / "settings.json"


class SettingsStore:
    """Read and atomically write one local JSON settings file."""

    def __init__(self, path: Path = DEFAULT_SETTINGS_PATH) -> None:
        self.path = path

    def load(self) -> dict[str, Any]:
        if not self.path.exists():
            return {}

        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("Could not load saved settings from %s: %s", self.path, exc)
            return {}

        if not isinstance(data, dict):
            logger.warning("Ignoring saved settings because the JSON root is not an object")
            return {}
        return data

    def save(self, settings: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = self.path.with_suffix(".tmp")
        payload = json.dumps(settings, indent=2, ensure_ascii=False)
        temporary_path.write_text(payload + "\n", encoding="utf-8")
        temporary_path.replace(self.path)


settings_store = SettingsStore()
