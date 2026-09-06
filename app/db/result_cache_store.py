"""Small local cache for downloaded nflverse weekly player-stat files."""
from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent.parent
DEFAULT_RESULT_CACHE_PATH = BASE_DIR / "data" / "result_cache.json"


class ResultCacheStore:
    """Persist provider responses so one check serves every matching tracked bet."""

    def __init__(self, path: Path = DEFAULT_RESULT_CACHE_PATH) -> None:
        self.path = path
        self._lock = threading.RLock()

    def get_nflverse_season(self, season: int) -> dict[str, str] | None:
        with self._lock:
            try:
                payload = json.loads(self.path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                return None
            record = payload.get("nflverse", {}).get(str(season)) if isinstance(payload, dict) else None
            if not isinstance(record, dict) or not isinstance(record.get("content"), str):
                return None
            return {"content": record["content"], "fetched_at": str(record.get("fetched_at") or "")}

    def save_nflverse_season(self, season: int, content: str) -> dict[str, str]:
        record = {"content": content, "fetched_at": datetime.now(timezone.utc).isoformat()}
        with self._lock:
            data: dict[str, object] = {"version": 1, "nflverse": {}}
            try:
                existing = json.loads(self.path.read_text(encoding="utf-8"))
                if isinstance(existing, dict) and existing.get("version") == 1:
                    data = existing
            except (OSError, json.JSONDecodeError):
                pass
            nflverse = data.setdefault("nflverse", {})
            if not isinstance(nflverse, dict):
                nflverse = {}
                data["nflverse"] = nflverse
            nflverse[str(season)] = record
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.path.with_suffix(".tmp")
            temporary.write_text(json.dumps(data, ensure_ascii=False) + "\n", encoding="utf-8")
            temporary.replace(self.path)
        return record


result_cache_store = ResultCacheStore()
