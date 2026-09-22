"""Local records for sportsbook bonus credits entered outside tracked promotions."""
from __future__ import annotations

import json
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).resolve().parent.parent.parent


class ManualBonusCreditStore:
    def __init__(self, path: Path = BASE_DIR / "data" / "manual_bonus_credits.json") -> None:
        self.path = path
        self._lock = threading.RLock()

    def list(self) -> list[dict[str, Any]]:
        with self._lock:
            try:
                data = (
                    json.loads(self.path.read_text(encoding="utf-8"))
                    if self.path.exists()
                    else {"credits": []}
                )
                return sorted(
                    data.get("credits", []),
                    key=lambda item: item["created_at"],
                    reverse=True,
                )
            except (OSError, json.JSONDecodeError): return []

    def create(self, amount: float, season: int | None, week: int | None) -> dict[str, Any]:
        credit = {
            "id": str(uuid.uuid4()),
            "amount": round(amount, 2),
            "season": season,
            "week": week,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        with self._lock:
            credits = self.list()
            credits.append(credit)
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.path.with_suffix(".tmp")
            temporary.write_text(
                json.dumps({"credits": credits}, indent=2) + "\n",
                encoding="utf-8",
            )
            temporary.replace(self.path)
        return credit


manual_bonus_credit_store = ManualBonusCreditStore()
