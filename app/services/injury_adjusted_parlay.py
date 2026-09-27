"""Receipt-only settlements when an injured parlay leg is removed and Bet365 pays bonus credit."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.db.parlay_tracker_store import parlay_tracker_store
from app.services.safety_net import parlay_week_context, ticket_title


def overview() -> dict[str, Any]:
    sources = []
    for parlay in parlay_tracker_store.list():
        settlement = parlay.get("injury_adjusted_parlay_settlement")
        if not settlement:
            continue
        season, week = parlay_week_context(parlay)
        sources.append({
            "id": parlay["id"], "description": ticket_title(parlay), "status": parlay["status"],
            "bet_type": parlay["bet_type"], "season": season, "week": week, "receipt": settlement,
        })
    return {"sources": sources}


def record_receipt(parlay_id: str, amount: float, injured_leg_index: int) -> dict[str, Any]:
    source = next((item for item in parlay_tracker_store.list() if item["id"] == parlay_id), None)
    if not source or source["status"] not in {"pending", "lost"}:
        raise ValueError("This injury-adjusted settlement can be recorded only for a pending or lost parlay.")
    if source.get("injury_adjusted_parlay_settlement"):
        raise ValueError("This parlay already has an injury-adjusted bonus-credit settlement.")
    if source.get("prop_protect_receipt"):
        raise ValueError("This parlay already has a Prop Protect bonus-credit settlement. Do not record two bonus credits.")
    legs = source.get("legs") or []
    if not 0 <= injured_leg_index < len(legs):
        raise ValueError("Choose the injured leg from this parlay.")
    if amount <= 0:
        raise ValueError("Enter the positive bonus-credit amount Bet365 actually issued.")
    if source["status"] == "pending":
        source = parlay_tracker_store.settle(parlay_id, "lost")
    injured = legs[injured_leg_index]
    receipt = {
        "amount": round(amount, 2),
        "injured_leg_index": injured_leg_index,
        "injured_leg_description": injured.get("description") or injured.get("player_name") or "Parlay leg",
        "remaining_legs_treated_as_won": True,
        "confirmed_at": datetime.now(timezone.utc).isoformat(),
    }
    return parlay_tracker_store.update(parlay_id, {"injury_adjusted_parlay_settlement": receipt})
