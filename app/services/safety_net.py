"""Safety-net promotion estimates and confirmed bonus-credit receipts."""
from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any

from app.db.parlay_tracker_store import parlay_tracker_store


def estimate(stake: float, winning_return: float, refund: float,
             conversion: float, probability: float | None = None) -> dict[str, Any]:
    values = (stake, winning_return, refund, conversion)
    if not all(math.isfinite(x) for x in values) or not (stake > 0 and winning_return >= stake and 0 < refund <= stake and 0 <= conversion <= 1):
        raise ValueError("Enter a positive stake, valid win return, refund no larger than stake, and conversion from 0% to 100%.")
    if probability is not None and (not math.isfinite(probability) or not 0 <= probability <= 1):
        raise ValueError("Win probability must be between 0 and 1.")
    bonus_value = refund * conversion
    denominator = winning_return - bonus_value
    result = {
        "estimated_bonus_cash_value": round(bonus_value, 4),
        "ordinary_break_even_probability": stake / winning_return,
        "break_even_probability": (stake - bonus_value) / denominator if denominator else 0,
        "ordinary_ev": None,
        "expected_promo_value": None,
        "adjusted_ev": None,
    }
    if probability is not None:
        ordinary = probability * winning_return - stake
        added = (1 - probability) * bonus_value
        result.update(ordinary_ev=round(ordinary, 4), expected_promo_value=round(added, 4), adjusted_ev=round(ordinary + added, 4))
    return result


def validate_record(record: dict[str, Any]) -> None:
    """Protect persisted receipts when a wager is corrected through any route."""
    offer = record.get("safety_net")
    receipt = record.get("safety_net_receipt")
    if offer:
        if record.get("bet_type") != "cash":
            raise ValueError("Remove the safety net before changing this parlay to a bonus bet.")
        estimate(float(record["stake"]), float(record["winning_total_return"]),
                 float(offer["refund_amount"]), float(offer["conversion_rate"]))
    if receipt and (not offer or record.get("status") != "lost"):
        raise ValueError("Correct the bonus receipt first before removing the safety net or changing the losing result.")
    if receipt and receipt["amount"] > offer["refund_amount"]:
        raise ValueError("The refund cannot be smaller than the confirmed bonus receipt.")


def parlay_week_context(source: dict[str, Any]) -> tuple[int | None, int | None]:
    """Use the parlay's saved week, or its unanimous leg context for older entries."""
    season, week = source.get("season"), source.get("week")
    if isinstance(season, int) and 2020 <= season <= 2100 and isinstance(week, int) and 1 <= week <= 25:
        return season, week
    contexts = []
    for leg in source.get("legs", []):
        identity = leg.get("result_identity") if isinstance(leg, dict) else None
        if not isinstance(identity, dict):
            return None, None
        leg_season, leg_week = identity.get("season"), identity.get("week")
        if not (isinstance(leg_season, int) and 2020 <= leg_season <= 2100 and isinstance(leg_week, int) and 1 <= leg_week <= 25):
            return None, None
        contexts.append((leg_season, leg_week))
    return contexts[0] if contexts and all(context == contexts[0] for context in contexts) else (None, None)


def overview() -> dict[str, Any]:
    """Return safety-net sources and their confirmed bonus-credit receipts."""
    parlays = parlay_tracker_store.list()
    sources = []
    for source in parlays:
        if not source.get("safety_net"):
            continue
        receipt = source.get("safety_net_receipt")
        season, week = parlay_week_context(source)
        sources.append({"id": source["id"], "description": ticket_title(source), "created_at": source["created_at"],
                        "season": season, "week": week,
                        "status": source["status"], "offer": source["safety_net"], "receipt": receipt,
                        })
    return {"sources": sources}


def ticket_title(ticket):
    return ticket.get("description") or (" / ".join(leg.get("description") or leg.get("player_name", "Leg") for leg in ticket["legs"]) if "legs" in ticket else ticket.get("player_name", "Bonus wager"))


def record_receipt(source_id: str, amount: float | None):
    with parlay_tracker_store._lock:
        source = next((p for p in parlay_tracker_store.list() if p["id"] == source_id), None)
        if source is None:
            raise ValueError("Safety-net parlay not found.")
        if not source.get("safety_net") or source["status"] != "lost" or source["bet_type"] != "cash":
            raise ValueError("Only a lost cash safety-net parlay can receive a bonus refund.")
        if amount is not None and (not math.isfinite(amount) or amount <= 0 or amount > source["safety_net"]["refund_amount"]):
            raise ValueError("Received amount must be positive and cannot exceed the expected refund.")
        receipt = {"amount": round(amount, 2), "confirmed_at": datetime.now(timezone.utc).isoformat()} if amount is not None else None
        history = [*source.get("safety_net_history", []), {"action": "receipt", "at": datetime.now(timezone.utc).isoformat(), "receipt": receipt}]
        return parlay_tracker_store.update(source_id, {"safety_net_receipt": receipt, "safety_net_history": history})
