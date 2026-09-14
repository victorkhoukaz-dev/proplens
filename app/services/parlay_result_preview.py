"""Preview-only result checks for every eligible leg of a tracked parlay."""
from __future__ import annotations

from typing import Any

from app.core.normalizer import PlayerNameNormalizer, TeamNormalizer
from app.services.result_preview import SUPPORTED_MARKETS, result_preview_service


class ParlayResultPreviewService:
    """Adapt saved parlay legs to the proven straight-bet preview service."""

    @staticmethod
    def _fallback_identity(parlay: dict[str, Any], leg: dict[str, Any]) -> dict[str, Any]:
        existing = leg.get("result_identity") if isinstance(leg.get("result_identity"), dict) else {}
        player_name = str(leg.get("player_name") or "").strip()
        team = TeamNormalizer.canonical_team(str(leg.get("team") or ""))
        opponent = TeamNormalizer.canonical_team(str(leg.get("opponent") or ""))
        return {
            **existing,
            "status": existing.get("status") or "manual_required",
            "season": existing.get("season") if isinstance(existing.get("season"), int) else parlay.get("season"),
            "week": existing.get("week") if isinstance(existing.get("week"), int) else parlay.get("week"),
            "player_key": existing.get("player_key") or PlayerNameNormalizer.clean_name(player_name),
            "team": existing.get("team") or team or None,
            "opponent": existing.get("opponent") or opponent or None,
        }

    @staticmethod
    def _manual_leg_preview(parlay_id: str, index: int, leg: dict[str, Any], message: str) -> dict[str, Any]:
        return {
            "leg_id": f"{parlay_id}:{index}",
            "player_name": leg.get("player_name") or leg.get("description") or "Parlay leg",
            "market": leg.get("market") or "manual",
            "line": leg.get("line"),
            "status": "manual_required",
            "message": message,
        }

    def preview(
        self,
        parlays: list[dict[str, Any]],
        *,
        refresh: bool = True,
        already_refreshed_seasons: set[int] | None = None,
    ) -> dict[str, Any]:
        pending = [parlay for parlay in parlays if parlay.get("status") == "pending"]
        candidates: list[dict[str, Any]] = []
        grouped: list[dict[str, Any]] = []

        for parlay in pending:
            previews: list[dict[str, Any] | None] = []
            for index, leg in enumerate(parlay.get("legs") or []):
                entry_mode = leg.get("entry_mode") or "evaluated"
                if entry_mode == "free_text":
                    previews.append(self._manual_leg_preview(parlay["id"], index, leg, "Manual settlement required — free-text parlay legs cannot be checked."))
                    continue
                if leg.get("category") not in {None, "player_prop"}:
                    previews.append(self._manual_leg_preview(parlay["id"], index, leg, "Manual settlement required — game and custom parlay legs are not in the tested result preview yet."))
                    continue
                if leg.get("market") not in set(SUPPORTED_MARKETS) | {"anytime_td"}:
                    previews.append(self._manual_leg_preview(parlay["id"], index, leg, "Manual settlement required — this parlay market is not in the tested final-stat preview yet."))
                    continue
                leg_id = f"{parlay['id']}:{index}"
                candidates.append(
                    {
                        "id": leg_id,
                        "status": "pending",
                        "entry_origin": "manual" if entry_mode == "structured" else "evaluated",
                        "player_name": leg.get("player_name") or leg.get("description") or "Parlay leg",
                        "market": leg.get("market"),
                        "side_label": leg.get("side_label") or "",
                        "line": leg.get("line"),
                        "result_identity": self._fallback_identity(parlay, leg),
                    }
                )
                previews.append(None)
            grouped.append({"parlay": parlay, "leg_previews": previews})

        report = result_preview_service.preview(
            candidates,
            refresh=refresh,
            already_refreshed_seasons=already_refreshed_seasons,
        )
        by_leg_id = {proposal["bet_id"]: proposal for proposal in report["proposals"]}
        results: list[dict[str, Any]] = []
        for group in grouped:
            parlay = group["parlay"]
            legs: list[dict[str, Any]] = []
            for index, preview in enumerate(group["leg_previews"]):
                if preview is None:
                    preview = by_leg_id.get(f"{parlay['id']}:{index}")
                if preview is None:
                    preview = self._manual_leg_preview(parlay["id"], index, parlay["legs"][index], "This leg could not be checked safely.")
                legs.append(preview)
            results.append({
                "parlay_id": parlay["id"],
                "description": parlay.get("description") or f"{len(legs)}-leg parlay",
                "legs": legs,
                **self._parlay_outcome(legs),
            })
        return {"preview_only": True, "checked_pending": len(pending), "sources": report["sources"], "parlays": results}

    @staticmethod
    def _parlay_outcome(legs: list[dict[str, Any]]) -> dict[str, str | None]:
        if not legs:
            return {"status": "manual_required", "proposed_result": None, "message": "Manual settlement required — this parlay has no checkable saved legs."}
        if any(leg.get("status") == "proposal" and leg.get("proposed_result") == "lost" for leg in legs):
            return {
                "status": "proposal",
                "proposed_result": "lost",
                "message": "At least one supported leg has final stats and lost, so this parlay lost. Preview only — confirm against Bet365 before settling.",
            }
        if not all(leg.get("status") == "proposal" for leg in legs):
            if any(leg.get("status") in {"stats_unavailable", "game_not_final", "source_error"} for leg in legs):
                return {"status": "waiting", "proposed_result": None, "message": "Waiting for final stats or a result source. This parlay remains pending."}
            return {"status": "needs_review", "proposed_result": None, "message": "Some legs cannot be checked safely. This parlay remains pending and needs manual settlement."}
        outcomes = {str(leg.get("proposed_result")) for leg in legs}
        if "push" in outcomes:
            return {"status": "push_review", "proposed_result": None, "message": "A leg pushed. Check Bet365's repriced payout, then settle this parlay manually."}
        if outcomes == {"won"}:
            return {"status": "proposal", "proposed_result": "won", "message": "Every leg has final stats and won. Preview only — confirm against Bet365 before settling."}
        return {"status": "needs_review", "proposed_result": None, "message": "The leg results need manual review."}


parlay_result_preview_service = ParlayResultPreviewService()
