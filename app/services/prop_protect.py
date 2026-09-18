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
    if "legs" in ticket:
        return ticket.get("description") or f"{len(ticket['legs'])}-leg parlay"
    return ticket.get("description") or ticket.get("player_name") or "Tracked bet"


def overview() -> dict[str, Any]:
    bets, parlays = bet_tracker_store.list(), parlay_tracker_store.list()
    destinations = {("straight", item["id"]): item for item in bets}
    destinations.update({("parlay", item["id"]): item for item in parlays})
    linked = set()
    sources = []
    for kind, tickets in (("straight", bets), ("parlay", parlays)):
        for source in tickets:
            receipt = source.get("prop_protect_receipt")
            if not receipt:
                continue
            links = []
            for link in source.get("prop_protect_links", []):
                key = (link["kind"], link["ticket_id"]); linked.add(key)
                ticket = destinations.get(key)
                valid = bool(ticket and ticket["bet_type"] == "bonus" and ticket["status"] != "cancelled" and abs(float(ticket["stake"]) - link["amount"]) < .005)
                links.append({**link, "needs_review": not valid, "description": _title(ticket) if ticket else "Missing wager", "status": ticket.get("status") if ticket else None, "cash_profit": ticket.get("profit") if valid else None})
            allocated = round(sum(link["amount"] for link in links), 2)
            season = source.get("season") or source.get("result_identity", {}).get("season")
            week = source.get("week") or source.get("result_identity", {}).get("week")
            if kind == "parlay" and (not season or not week):
                contexts = [(leg.get("result_identity", {}).get("season"), leg.get("result_identity", {}).get("week")) for leg in source.get("legs", [])]
                if contexts and all(context == contexts[0] for context in contexts): season, week = contexts[0]
            sources.append({"kind": kind, "id": source["id"], "description": _title(source), "status": source["status"], "season": season, "week": week, "receipt": receipt, "remaining": round(receipt["amount"] - allocated, 2), "links": links})
    candidates = [{"kind": kind, "ticket_id": id_, "description": _title(ticket), "stake": ticket["stake"], "status": ticket["status"]} for (kind, id_), ticket in destinations.items() if ticket["bet_type"] == "bonus" and ticket["status"] != "cancelled" and (kind, id_) not in linked]
    return {"sources": sources, "candidates": candidates}


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


def link_bonus(kind: Kind, source_id: str, target_kind: Kind, ticket_id: str, unlink: bool = False) -> dict[str, Any]:
    source_store, target_store = _store(kind), _store(target_kind)
    source = next((item for item in source_store.list() if item["id"] == source_id), None)
    if not source or not source.get("prop_protect_receipt"):
        raise ValueError("Record the Prop Protect bonus credit first.")
    target = next((item for item in target_store.list() if item["id"] == ticket_id), None)
    if not target or target["bet_type"] != "bonus":
        raise ValueError("Choose a tracked bonus wager.")
    links = list(source.get("prop_protect_links", [])); key = (target_kind, ticket_id)
    if unlink:
        return source_store.update(source_id, {"prop_protect_links": [link for link in links if (link["kind"], link["ticket_id"]) != key]})
    if any((link["kind"], link["ticket_id"]) == key for link in links): return source
    if float(target["stake"]) > float(source["prop_protect_receipt"]["amount"]) - sum(float(link["amount"]) for link in links) + .005:
        raise ValueError("This bonus wager is larger than the unlinked Prop Protect credit.")
    return source_store.update(source_id, {"prop_protect_links": [*links, {"kind": target_kind, "ticket_id": ticket_id, "amount": round(float(target["stake"]), 2)}]})
