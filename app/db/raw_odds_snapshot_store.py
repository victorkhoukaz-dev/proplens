"""Local diagnostic persistence for pre-normalization OddsPapi responses."""
from __future__ import annotations

import json
import re
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


BASE_DIR = Path(__file__).resolve().parent.parent.parent
DEFAULT_RAW_ODDS_DIRECTORY = BASE_DIR / "data" / "oddspapi_raw"

_SENSITIVE_KEY_PARTS = ("apikey", "api_key", "authorization", "token", "secret")
_API_KEY_QUERY_PATTERN = re.compile(r"(?i)(api[_-]?key=)[^&\s\"']+")


def _redact_secrets(value: Any) -> Any:
    """Copy JSON-compatible data while removing credential-like values."""
    if isinstance(value, list):
        return [_redact_secrets(item) for item in value]
    if isinstance(value, dict):
        cleaned: dict[str, Any] = {}
        for key, item in value.items():
            normalized_key = str(key).lower().replace("-", "_")
            if any(part in normalized_key for part in _SENSITIVE_KEY_PARTS):
                cleaned[str(key)] = "[REDACTED]"
            else:
                cleaned[str(key)] = _redact_secrets(item)
        return cleaned
    if isinstance(value, str):
        return _API_KEY_QUERY_PATTERN.sub(r"\1[REDACTED]", value)
    return value


class RawOddsSnapshotStore:
    """Atomically save one timestamped, secret-redacted provider snapshot."""

    def __init__(self, directory: Path = DEFAULT_RAW_ODDS_DIRECTORY) -> None:
        self.directory = directory
        self._lock = threading.RLock()

    def save(
        self,
        *,
        bookmaker_responses: dict[str, Any],
        market_catalog_response: Any | None,
        parsed_market_catalog: dict[str, Any],
        request_metadata: dict[str, Any],
    ) -> Path:
        captured_at = datetime.now(timezone.utc)
        payload = {
            "version": 1,
            "captured_at": captured_at.isoformat(),
            "provider": "oddspapi",
            "request": _redact_secrets(request_metadata),
            "market_catalog_response": _redact_secrets(market_catalog_response),
            "parsed_market_catalog": _redact_secrets(parsed_market_catalog),
            "bookmaker_responses": _redact_secrets(bookmaker_responses),
        }
        serialized = json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
        filename = f"oddspapi_raw_{captured_at.strftime('%Y%m%d_%H%M%S_%f')}.json"

        with self._lock:
            self.directory.mkdir(parents=True, exist_ok=True)
            destination = self.directory / filename
            temporary = self.directory / f"{filename}.tmp"
            temporary.write_text(serialized, encoding="utf-8")
            temporary.replace(destination)
        return destination


raw_odds_snapshot_store = RawOddsSnapshotStore()
