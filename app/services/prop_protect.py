"""Bet365 Prop Protect bonus-credit settlements for cash bets and parlays."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from app.db.bet_tracker_store import bet_tracker_store
from app.db.parlay_tracker_store import parlay_tracker_store

Kind = Literal["straight", "parlay"]


def _store(kind: Kind):
    return bet_tracker_store if kind == "straight" else parlay_tracker_store


def _title(ticket: dict[str, Any]) -> str:
    if ticket.get("description"):
        return ticket["description"]
    if "legs" in ticket:
        return " / ".join(
            leg.get("description") or leg.get("player_name", "Leg")
            for leg in ticket["legs"]
        )
    return ticket.get("player_name") or "Tracked bet"


def overview() -> dict[str, Any]:
    bets, parlays = bet_tracker_store.list(), parlay_tracker_store.list()
    sources = []
    for kind, tickets in (("straight", bets), ("parlay", parlays)):
        for source in tickets:
            receipt = source.get("prop_protect_receipt")
            if not receipt:
                continue
            season = source.get("season") or source.get("result_identity", {}).get("season")
            week = source.get("week") or source.get("result_identity", {}).get("week")
            if kind == "parlay" and (not season or not week):
                contexts = [(leg.get("result_identity", {}).get("season"), leg.get("result_identity", {}).get("week")) for leg in source.get("legs", [])]
                if contexts and all(context == contexts[0] for context in contexts): season, week = contexts[0]
            sources.append({"kind": kind, "id": source["id"], "description": _title(source), "status": source["status"], "season": season, "week": week, "receipt": receipt})
    return {"sources": sources}


def record_receipt(kind: Kind, source_id: str, trigger: str, amount: float) -> dict[str, Any]:
    if trigger not in {"injury_void", "bonus_cashout"} or amount <= 0:
        raise ValueError("Choose the Prop Protect outcome and enter the actual positive bonus amount.")
    store = _store(kind)
    source = next((item for item in store.list() if item["id"] == source_id), None)
    if not source or source["bet_type"] != "cash" or source["status"] in {"won", "cancelled"}:
        raise ValueError("Prop Protect can be recorded only for a cash bet or parlay that did not pay cash.")
    if source["status"] == "pending":
        source = store.settle(source_id, "lost")
    receipt = {"amount": round(amount, 2), "trigger": trigger, "confirmed_at": datetime.now(timezone.utc).isoformat()}
    return store.update(source_id, {"prop_protect_receipt": receipt})
