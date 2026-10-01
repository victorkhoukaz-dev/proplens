"""Explicitly requested, conservative settlement of ordinary offensive straights."""
from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any

from app.db.bet_tracker_store import bet_tracker_store, TrackedBetNotFoundError
from app.services.model_research import model_research_service
from app.services.result_preview import _identity_ready

AUTO_MARKETS = frozenset({
    "passing_yards", "rushing_yards", "rushing_receiving_yards",
    "rushing_attempts", "receiving_yards", "receptions",
})


def eligible(bet: dict[str, Any]) -> bool:
    try:
        line = float(bet["line"])
        stake, odds = float(bet["stake"]), float(bet["decimal_odds"])
    except (KeyError, TypeError, ValueError):
        return False
    return (
        bet.get("status") == "pending"
        and bet.get("market") in AUTO_MARKETS
        and bet.get("category") in {None, "player_prop"}
        and str(bet.get("side_label", "")).lower() in {"over", "under"}
        and math.isfinite(line) and line >= 0 and line % 1 == 0.5
        and math.isfinite(stake) and stake > 0
        and math.isfinite(odds) and odds > 1
        and bet.get("bet_type") in {"cash", "bonus"}
        and _identity_ready(bet) is not None
        and not any(bet.get(key) for key in (
            "safety_net", "prop_protect", "injury_settlement", "settlement_amount",
            "profit_boost_pct", "actual_total_return",
        ))
    )


def settle_eligible(bets: list[dict[str, Any]], report: dict[str, Any]) -> dict[str, Any]:
    """Use freshly fetched evidence; never settle on stale provider fallback."""
    result: dict[str, Any] = {"settled": [], "skipped": [], "won": 0, "lost": 0}
    candidates = [bet for bet in bets if eligible(bet)]
    if not candidates:
        return result
    try:
        content, fetched_at, used_cache = model_research_service._schedule_content(refresh=True)
        if used_cache:
            raise ValueError("Schedule refresh failed; cached completion evidence is review-only.")
        games = model_research_service._schedule_rows(content)
    except Exception:
        result["skipped"] = [{"bet_id": bet["id"], "reason": "Fresh completed-game evidence unavailable; review manually."} for bet in candidates]
        return result
    proposals = {item["bet_id"]: item for item in report["proposals"]}
    sources = {item["season"]: item for item in report.get("sources", [])}
    for bet in candidates:
        identity = bet["result_identity"]
        proposal = proposals.get(bet["id"], {})
        source = sources.get(identity["season"], {})
        matches = [game for game in games if
                   game["season"] == identity["season"] and game["week"] == identity["week"]
                   and {game["home"], game["away"]} == {identity["team"], identity["opponent"]}]
        reason = None
        if source.get("used_cache", True):
            reason = "Fresh player statistics unavailable; cached suggestions remain review-only."
        elif len(matches) != 1 or not matches[0]["completed"] or matches[0]["kickoff"] >= datetime.now(timezone.utc):
            reason = "The schedule does not uniquely confirm a completed game."
        elif proposal.get("status") != "proposal" or proposal.get("proposed_result") not in {"won", "lost"}:
            reason = "No exact usable player-stat result; review manually."
        elif not math.isfinite(float(proposal["actual_stat"])):
            reason = "Invalid player statistic; review manually."
        elif not proposal.get("participation_confirmed"):
            reason = "Player participation is not confirmed by recorded offensive activity; review possible voids manually."
        if reason:
            result["skipped"].append({"bet_id": bet["id"], "reason": reason})
            continue
        evidence = {
            "version": 1, "mode": "automatic", "source": "nflverse",
            "source_fetched_at": source.get("fetched_at"), "schedule_fetched_at": fetched_at,
            "season": identity["season"], "week": identity["week"],
            "team": identity["team"], "opponent": identity["opponent"],
            "player_key": identity["player_key"], "line": bet["line"], "side": bet["side_label"],
            "actual_stat": proposal["actual_stat"], "stat_label": proposal["stat_label"],
            "proposed_result": proposal["proposed_result"], "game_completed": True,
            "reason": "User-enabled Check results: fresh exact player/stat match and completed schedule game.",
        }
        try:
            saved = bet_tracker_store.settle(bet["id"], proposal["proposed_result"], evidence=evidence, expected_record=bet)
        except (ValueError, TrackedBetNotFoundError):
            result["skipped"].append({"bet_id": bet["id"], "reason": "The bet changed during checking; it was not automatically settled."})
            continue
        result["settled"].append({"bet_id": bet["id"], "player_name": bet["player_name"], "result": saved["status"], "actual_stat": proposal["actual_stat"]})
        result[saved["status"]] += 1
    return result
