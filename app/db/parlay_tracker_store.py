"""Atomic local storage for Phase 3C tracked parlays."""
from __future__ import annotations

import json
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


BASE_DIR = Path(__file__).resolve().parent.parent.parent
DEFAULT_PARLAY_TRACKER_PATH = BASE_DIR / "data" / "tracked_parlays.json"


class TrackedParlayNotFoundError(KeyError):
    pass


class ParlayTrackerStore:
    def __init__(self, path: Path = DEFAULT_PARLAY_TRACKER_PATH) -> None:
        self.path = path
        self._lock = threading.RLock()

    def _read(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            return data.get("parlays", []) if isinstance(data, dict) and data.get("version") == 1 else []
        except (OSError, json.JSONDecodeError):
            return []

    def _write(self, parlays: list[dict[str, Any]]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = self.path.with_suffix(".tmp")
        temporary_path.write_text(json.dumps({"version": 1, "parlays": parlays}, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        temporary_path.replace(self.path)

    def list(self) -> list[dict[str, Any]]:
        with self._lock:
            return sorted(self._read(), key=lambda item: item["created_at"], reverse=True)

    def create(self, parlay: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            parlays = self._read()
            saved = {**parlay, "id": str(uuid.uuid4()), "status": "pending", "profit": None, "created_at": datetime.now(timezone.utc).isoformat(), "settled_at": None, "settlement_amount": None, "settlement_history": []}
            parlays.append(saved)
            self._write(parlays)
            return saved

    @staticmethod
    def winning_cash_payout(parlay: dict[str, Any]) -> float:
        """Return the cash actually paid if this parlay wins.

        Older bonus parlays stored the gross decimal-odds return, including the
        non-returned bonus stake. New bonus parlays store only the cash payout.
        The explicit flag keeps both formats safe without rewriting history.
        """
        winning_return = float(parlay["winning_total_return"])
        if parlay["bet_type"] == "bonus" and parlay.get("winning_return_includes_stake") is not False:
            return round(winning_return - float(parlay["stake"]), 2)
        return round(winning_return, 2)

    @staticmethod
    def _profit(parlay: dict[str, Any], status: str, settlement_amount: float | None = None) -> float:
        stake = float(parlay["stake"])
        if status == "won":
            payout = ParlayTrackerStore.winning_cash_payout(parlay)
            return payout if parlay["bet_type"] == "bonus" else round(payout - stake, 2)
        if status == "lost":
            return 0.0 if parlay["bet_type"] == "bonus" else round(-stake, 2)
        if status in {"cashed_out", "push_adjusted", "void_adjusted"}:
            if settlement_amount is None:
                raise ValueError("Enter the actual amount paid by Bet365 for this outcome.")
            return round(settlement_amount if parlay["bet_type"] == "bonus" else settlement_amount - stake, 2)
        return 0.0

    def settle(self, parlay_id: str, status: str, settlement_amount: float | None = None) -> dict[str, Any]:
        with self._lock:
            parlays = self._read()
            for parlay in parlays:
                if parlay["id"] != parlay_id:
                    continue
                profit = self._profit(parlay, status, settlement_amount)
                settled_at = datetime.now(timezone.utc).isoformat()
                history = list(parlay.get("settlement_history") or [])
                history.append({"at": settled_at, "status": status, "settlement_amount": settlement_amount, "source": "manual"})
                parlay.update({"status": status, "profit": profit, "settlement_amount": settlement_amount, "settled_at": settled_at, "settlement_history": history})
                self._write(parlays)
                return parlay
        raise TrackedParlayNotFoundError(parlay_id)

    def update(self, parlay_id: str, changes: dict[str, Any]) -> dict[str, Any]:
        """Correct financial details or the recorded result without changing the legs."""
        with self._lock:
            parlays = self._read()
            for parlay in parlays:
                if parlay["id"] != parlay_id:
                    continue
                parlay.update(changes)
                status = parlay["status"]
                if status == "pending":
                    parlay.update({"profit": None, "settlement_amount": None, "settled_at": None})
                else:
                    parlay["profit"] = self._profit(parlay, status, parlay.get("settlement_amount"))
                    parlay["settled_at"] = parlay.get("settled_at") or datetime.now(timezone.utc).isoformat()
                self._write(parlays)
                return parlay
        raise TrackedParlayNotFoundError(parlay_id)

    def delete(self, parlay_id: str) -> None:
        with self._lock:
            parlays = self._read()
            remaining = [parlay for parlay in parlays if parlay["id"] != parlay_id]
            if len(remaining) == len(parlays):
                raise TrackedParlayNotFoundError(parlay_id)
            self._write(remaining)

    def summary(self, include_pending: bool = True) -> dict[str, float | int | None]:
        parlays = self.list()
        settled = [parlay for parlay in parlays if parlay["status"] != "pending"]
        wagered = parlays if include_pending else settled
        cash_wagered = [parlay for parlay in wagered if parlay["bet_type"] == "cash" and parlay["status"] != "cancelled"]
        cash_settled = [parlay for parlay in settled if parlay["bet_type"] == "cash" and parlay["status"] != "cancelled"]
        bonus_settled = [parlay for parlay in settled if parlay["bet_type"] == "bonus" and parlay["status"] != "cancelled"]
        bonus_wagered = [parlay for parlay in wagered if parlay["bet_type"] == "bonus" and parlay["status"] != "cancelled"]
        cash_staked = round(sum(float(parlay["stake"]) for parlay in cash_settled), 2)
        cash_profit = round(sum(float(parlay["profit"] or 0) for parlay in cash_settled), 2)
        bonus_profit = round(sum(float(parlay["profit"] or 0) for parlay in bonus_settled), 2)
        total_profit = round(cash_profit + bonus_profit, 2)
        return {
            "total_parlays": len(parlays),
            "pending": len(parlays) - len(settled),
            "cash_wagered": round(sum(float(parlay["stake"]) for parlay in cash_wagered), 2),
            "cash_staked": cash_staked,
            "bonus_value_used": round(sum(float(parlay["stake"]) for parlay in bonus_wagered), 2),
            "cash_profit": cash_profit,
            "bonus_profit": bonus_profit,
            "total_profit": total_profit,
            "cash_roi_pct": round(cash_profit / cash_staked * 100, 2) if cash_staked else None,
            "total_roi_on_cash_risk_pct": round(total_profit / cash_staked * 100, 2) if cash_staked else None,
        }


parlay_tracker_store = ParlayTrackerStore()
