"""Atomic local storage for the Phase 2A straight-bet tracker."""
from __future__ import annotations

import json
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


BASE_DIR = Path(__file__).resolve().parent.parent.parent
DEFAULT_BET_TRACKER_PATH = BASE_DIR / "data" / "tracked_bets.json"


class TrackedBetNotFoundError(KeyError):
    pass


class BetTrackerStore:
    def __init__(self, path: Path = DEFAULT_BET_TRACKER_PATH) -> None:
        self.path = path
        self._lock = threading.RLock()

    def _read(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            return data.get("bets", []) if isinstance(data, dict) and data.get("version") == 1 else []
        except (OSError, json.JSONDecodeError):
            return []

    def _write(self, bets: list[dict[str, Any]]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = self.path.with_suffix(".tmp")
        temporary_path.write_text(json.dumps({"version": 1, "bets": bets}, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        temporary_path.replace(self.path)

    def list(self) -> list[dict[str, Any]]:
        with self._lock:
            return sorted(self._read(), key=lambda item: item["created_at"], reverse=True)

    def create(self, bet: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            bets = self._read()
            saved = {**bet, "id": str(uuid.uuid4()), "status": "pending", "profit": None, "created_at": datetime.now(timezone.utc).isoformat(), "settled_at": None}
            bets.append(saved)
            self._write(bets)
            return saved

    @staticmethod
    def _profit(bet: dict[str, Any], status: str, settlement_amount: float | None = None) -> float:
        stake = float(bet["stake"])
        if status == "won":
            return round(stake * (float(bet["decimal_odds"]) - 1), 2)
        if status == "lost":
            return 0.0 if bet["bet_type"] == "bonus" else round(-stake, 2)
        if status == "cashed_out":
            if settlement_amount is None:
                raise ValueError("Enter the actual cash-out amount.")
            return round(settlement_amount if bet["bet_type"] == "bonus" else settlement_amount - stake, 2)
        return 0.0

    def settle(self, bet_id: str, status: str, settlement_amount: float | None = None) -> dict[str, Any]:
        with self._lock:
            bets = self._read()
            for bet in bets:
                if bet["id"] != bet_id:
                    continue
                profit = self._profit(bet, status, settlement_amount)
                bet.update({"status": status, "profit": profit, "settlement_amount": settlement_amount, "settled_at": datetime.now(timezone.utc).isoformat()})
                self._write(bets)
                return bet
        raise TrackedBetNotFoundError(bet_id)

    def update(self, bet_id: str, changes: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            bets = self._read()
            for bet in bets:
                if bet["id"] != bet_id:
                    continue
                bet.update(changes)
                if bet["status"] != "pending":
                    bet["profit"] = self._profit(bet, bet["status"], bet.get("settlement_amount"))
                self._write(bets)
                return bet
        raise TrackedBetNotFoundError(bet_id)

    def summary(self) -> dict[str, float | int]:
        bets = self.list()
        settled = [bet for bet in bets if bet["status"] != "pending"]
        cash = [bet for bet in settled if bet["bet_type"] == "cash"]
        bonus = [bet for bet in settled if bet["bet_type"] == "bonus"]
        cash_staked = round(sum(float(bet["stake"]) for bet in cash), 2)
        cash_profit = round(sum(float(bet["profit"] or 0) for bet in cash), 2)
        bonus_profit = round(sum(float(bet["profit"] or 0) for bet in bonus), 2)
        return {"total_bets": len(bets), "pending": len(bets) - len(settled), "cash_staked": cash_staked, "cash_profit": cash_profit, "bonus_stake_used": round(sum(float(bet["stake"]) for bet in bonus), 2), "bonus_profit": bonus_profit, "total_profit": round(cash_profit + bonus_profit, 2), "cash_roi_pct": round((cash_profit / cash_staked * 100) if cash_staked else 0, 2)}


bet_tracker_store = BetTrackerStore()
