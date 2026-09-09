"""Local, reference-only NFL player directory for faster manual bet entry."""
from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


BASE_DIR = Path(__file__).resolve().parent.parent.parent
DEFAULT_PLAYER_DIRECTORY_PATH = BASE_DIR / "data" / "player_directory.json"


class PlayerDirectoryStore:
    def __init__(self, path: Path = DEFAULT_PLAYER_DIRECTORY_PATH) -> None:
        self.path = path
        self._lock = threading.RLock()

    def _read(self) -> dict[str, Any]:
        if not self.path.exists():
            return {"updated_at": None, "players": []}
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(data, dict) or data.get("version") != 1 or not isinstance(data.get("players"), list):
                raise ValueError("unsupported player directory")
            return {"updated_at": data.get("updated_at"), "players": data["players"]}
        except (OSError, ValueError, json.JSONDecodeError):
            return {"updated_at": None, "players": []}

    def _write(self, players: list[dict[str, str]]) -> dict[str, Any]:
        updated_at = datetime.now(timezone.utc).isoformat()
        payload = {"version": 1, "updated_at": updated_at, "players": players}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = self.path.with_suffix(".tmp")
        temporary_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        temporary_path.replace(self.path)
        return {"updated_at": updated_at, "players": players}

    def summary(self) -> dict[str, Any]:
        with self._lock:
            data = self._read()
            positions = sorted({str(player.get("position") or "") for player in data["players"] if player.get("position")})
            teams = sorted({str(player.get("team") or "") for player in data["players"] if player.get("team")})
            return {"count": len(data["players"]), "updated_at": data["updated_at"], "positions": positions, "team_count": len(teams)}

    def replace(self, players: list[dict[str, str]]) -> dict[str, Any]:
        with self._lock:
            return self._write(players)

    def clear(self) -> None:
        with self._lock:
            self._write([])

    def search(self, query: str, limit: int = 20) -> list[dict[str, str]]:
        normalized_query = query.casefold().strip()
        with self._lock:
            players = self._read()["players"]
        matches = [
            player for player in players
            if not normalized_query
            or normalized_query in str(player.get("player_name") or "").casefold()
            or normalized_query in str(player.get("team") or "").casefold()
        ]
        return sorted(matches, key=lambda player: (player["player_name"].casefold(), player["team"]))[:limit]


player_directory_store = PlayerDirectoryStore()
