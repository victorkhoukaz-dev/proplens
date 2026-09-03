"""
app.api.routes: REST API endpoints for opportunities, uploads, breakdowns, and settings.
"""
from __future__ import annotations

import asyncio
import io
import json
import logging
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel, field_validator

from datetime import datetime, timezone

from app.adapters.csv_odds_adapter import CSVOddsAdapter
from app.adapters.fantasypoints import FantasyPointsAdapter
from app.adapters.oddspapi_adapter import OddsPapiAdapter
from app.core.normalizer import PlayerNameNormalizer, TeamNormalizer
from app.core.distributions import DistributionEngine, DistributionType
from app.core.ev import EVEngine, KellyConfig
from app.db.bet_tracker_store import TrackedBetNotFoundError, bet_tracker_store
from app.db.cache import cache
from app.db.loaded_data_store import loaded_data_store
from app.db.projection_snapshot_store import (
    ProjectionSnapshotNotFoundError,
    projection_snapshot_store,
)
from app.db.raw_odds_snapshot_store import raw_odds_snapshot_store
from app.db.settings_store import settings_store
from app.schemas.ev import MatchedEVOpportunity, PropBreakdown
from app.schemas.projections import PlayerProjection, Position, StatCategory
from app.schemas.odds import (
    Bookmaker,
    Event,
    MarketOffer,
    MarketOutcome,
    OddsValue,
    OutcomeType,
)
from app.services.ev_pipeline import pipeline_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["EV Betting API"])



def persist_loaded_data() -> None:
    """Save the current normalized inputs or clearly fail the request."""
    try:
        loaded_data_store.save(cache.get_events(), cache.get_projections())
    except OSError as exc:
        logger.error("Could not persist loaded odds/projections: %s", exc)
        raise HTTPException(
            status_code=500,
            detail="The data loaded, but it could not be saved on this computer.",
        ) from exc


class SettingsUpdateRequest(BaseModel):
    bankroll: float | None = None
    kelly_fraction: float | None = None
    w_market: float | None = None
    w_model: float | None = None
    min_ev_threshold: float | None = None
    min_stake: float | None = None
    odds_api_key: str | None = None
    auto_refresh_seconds: int | None = None

    @field_validator("odds_api_key")
    @classmethod
    def validate_odds_api_key(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        lowered = cleaned.lower()
        looks_like_error = (
            lowered.startswith("error")
            or lowered.startswith("❌")
            or "live fetch failed" in lowered
            or lowered.startswith("http://")
            or lowered.startswith("https://")
            or "\n" in cleaned
            or "\r" in cleaned
        )
        if looks_like_error:
            raise ValueError("Paste only the OddsPapi API key, not an error message or URL.")
        return cleaned


class PasteUploadRequest(BaseModel):
    data_type: str = "projections"  # "projections" or "odds"
    content: str
    season: int = 2026
    week: int = 1
    label: str | None = None


EVALUATOR_MARKETS: tuple[StatCategory, ...] = (
    StatCategory.PASSING_YARDS,
    StatCategory.PASSING_TDS,
    StatCategory.PASSING_INTERCEPTIONS,
    StatCategory.RUSHING_YARDS,
    StatCategory.RECEIVING_YARDS,
    StatCategory.RECEPTIONS,
    StatCategory.ANYTIME_TD,
)


class PropEvaluationRequest(BaseModel):
    """A manually entered Bet365 prop evaluated solely from a loaded projection."""

    player_name: str
    stat_category: StatCategory
    side: Literal["over", "under", "yes"]
    line: float
    odds: float | int | str
    stake: float | None = None

    @field_validator("player_name")
    @classmethod
    def validate_player_name(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Choose a player before evaluating a prop.")
        return cleaned

    @field_validator("line")
    @classmethod
    def validate_line(cls, value: float) -> float:
        if value < 0:
            raise ValueError("The Bet365 line cannot be negative.")
        return value

    @field_validator("stake")
    @classmethod
    def validate_stake(cls, value: float | None) -> float | None:
        if value is not None and value < 0:
            raise ValueError("Stake cannot be negative.")
        return value


class TrackedBetCreateRequest(BaseModel):
    player_name: str
    team: str
    opponent: str | None = None
    market: str
    side_label: str
    line: float
    decimal_odds: float
    stake: float
    bet_type: Literal["cash", "bonus"]
    projection_mean: float
    model_win_probability: float
    model_fair_decimal: float
    expected_value_pct: float
    source_context: dict[str, Any] | None = None

    @field_validator("stake")
    @classmethod
    def validate_tracker_stake(cls, value: float) -> float:
        if value <= 0:
            raise ValueError("Enter a stake greater than $0 to save a bet.")
        return value

    @field_validator("decimal_odds")
    @classmethod
    def validate_tracker_odds(cls, value: float) -> float:
        if value <= 1:
            raise ValueError("Decimal odds must be above 1.00.")
        return value


class TrackedBetSettleRequest(BaseModel):
    status: Literal["won", "lost", "push", "cashed_out", "cancelled"]
    settlement_amount: float | None = None

    @field_validator("settlement_amount")
    @classmethod
    def validate_settlement_amount(cls, value: float | None) -> float | None:
        if value is not None and value < 0:
            raise ValueError("Cash-out amount cannot be negative.")
        return value


class TrackedBetUpdateRequest(BaseModel):
    stake: float | None = None
    bet_type: Literal["cash", "bonus"] | None = None
    line: float | None = None
    decimal_odds: float | None = None

    @field_validator("stake")
    @classmethod
    def validate_updated_stake(cls, value: float | None) -> float | None:
        if value is not None and value <= 0:
            raise ValueError("Stake must be greater than $0.")
        return value

    @field_validator("decimal_odds")
    @classmethod
    def validate_updated_odds(cls, value: float | None) -> float | None:
        if value is not None and value <= 1:
            raise ValueError("Decimal odds must be above 1.00.")
        return value


@router.get("/health")
def health_check() -> dict[str, str]:
    return {"status": "ok", "app": "PropLens Manual NFL Prop Evaluator"}


@router.get("/settings")
def get_settings() -> dict[str, Any]:
    return cache.get_settings().to_dict()


def _projection_key(projection: PlayerProjection) -> str:
    return PlayerNameNormalizer.clean_name(
        projection.canonical_name or projection.player_name
    ).lower()


def _evaluator_projection(player_name: str, stat_category: StatCategory) -> PlayerProjection | None:
    requested_name = PlayerNameNormalizer.clean_name(player_name).lower()
    for projection in cache.get_projections():
        if projection.stat_category == stat_category and _projection_key(projection) == requested_name:
            return projection
    return None


def _activate_projection_snapshot(snapshot_id: str) -> dict[str, Any]:
    try:
        snapshot = projection_snapshot_store.activate(snapshot_id)
    except ProjectionSnapshotNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Projection set not found.") from exc
    cache.replace_projections(snapshot.projections)
    persist_loaded_data()
    pipeline_service.process_data()
    return {"success": True, "active_snapshot": snapshot.summary(snapshot.id)}


def _save_projection_import(
    projections: list[PlayerProjection], *, label: str | None, source: str, season: int, week: int
) -> dict[str, Any]:
    if not 2020 <= season <= 2100:
        raise HTTPException(status_code=400, detail="Season must be between 2020 and 2100.")
    if not 1 <= week <= 25:
        raise HTTPException(status_code=400, detail="Week must be between 1 and 25.")
    try:
        snapshot = projection_snapshot_store.create(
            projections,
            label=label or f"{source} — {season} Week {week}",
            source=source,
            season=season,
            week=week,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    cache.replace_projections(snapshot.projections)
    persist_loaded_data()
    pipeline_service.process_data()
    return {"snapshot": snapshot.summary(snapshot.id), "count": len(projections)}


@router.get("/projection-library")
def get_projection_library() -> dict[str, Any]:
    return projection_snapshot_store.list_summaries()


@router.post("/projection-library/{snapshot_id}/activate")
def activate_projection_library_snapshot(snapshot_id: str) -> dict[str, Any]:
    return _activate_projection_snapshot(snapshot_id)


@router.delete("/projection-library/{snapshot_id}")
def delete_projection_library_snapshot(snapshot_id: str) -> dict[str, Any]:
    try:
        projection_snapshot_store.delete(snapshot_id)
    except ProjectionSnapshotNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Projection set not found.") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"success": True, "message": "Archived projection set permanently deleted."}


@router.get("/evaluator/players")
def get_evaluator_players(q: str = Query("", max_length=80), limit: int = Query(12, ge=1, le=30)) -> dict[str, Any]:
    """Return projection-backed player choices for the manual evaluator."""
    query = q.strip().lower()
    players: dict[str, dict[str, Any]] = {}

    for projection in cache.get_projections():
        if projection.stat_category not in EVALUATOR_MARKETS:
            continue
        display_name = projection.canonical_name or projection.player_name
        search_text = f"{display_name} {projection.team} {projection.position}".lower()
        if query and query not in search_text:
            continue

        key = _projection_key(projection)
        player = players.setdefault(
            key,
            {
                "player_name": display_name,
                "team": projection.team,
                "opponent": projection.opponent,
                "position": projection.position,
                "markets": [],
                "projections": {},
            },
        )
        if projection.stat_category.value not in player["markets"]:
            player["markets"].append(projection.stat_category.value)
        player["projections"][projection.stat_category.value] = projection.projection_mean

    ordered = sorted(players.values(), key=lambda player: player["player_name"].lower())[:limit]
    library = projection_snapshot_store.list_summaries()
    active_context = next(
        (snapshot for snapshot in library["snapshots"] if snapshot["active"]),
        None,
    )
    return {
        "players": ordered,
        "projection_count": len(cache.get_projections()),
        "projection_context": active_context,
    }


@router.post("/evaluator/evaluate")
def evaluate_manual_prop(payload: PropEvaluationRequest) -> dict[str, Any]:
    """Evaluate one manual Bet365 player prop from an exact loaded projection.

    This route never fetches odds, persists a bet, or synthesizes a sharp-market signal.
    """
    if payload.stat_category not in EVALUATOR_MARKETS:
        raise HTTPException(status_code=400, detail="This market is not available in the first evaluator release.")
    if payload.stat_category == StatCategory.ANYTIME_TD and payload.side != "yes":
        raise HTTPException(status_code=400, detail="Anytime touchdown is evaluated as a Yes price in this release.")
    if payload.stat_category != StatCategory.ANYTIME_TD and payload.side == "yes":
        raise HTTPException(status_code=400, detail="Choose Over or Under for this prop market.")

    odds_value = _parse_odds_val(payload.odds)
    if not odds_value:
        raise HTTPException(status_code=400, detail="Enter valid American odds such as -110 or +120, or decimal odds above 1.00.")

    projection = _evaluator_projection(payload.player_name, payload.stat_category)
    if not projection:
        raise HTTPException(
            status_code=404,
            detail="No matching projection is loaded for this player and market. Import projections or choose another market.",
        )

    try:
        if payload.stat_category.is_continuous:
            position = Position(projection.position) if projection.position in Position._value2member_map_ else Position.WR
            distribution = DistributionEngine.evaluate_continuous_prop(
                projection_mean=projection.projection_mean,
                line=payload.line,
                position=position,
                stat_category=payload.stat_category,
                dist_type=DistributionType.LOG_NORMAL,
                cv_override=projection.projection_std,
            )
        else:
            distribution = DistributionEngine.evaluate_discrete_prop(
                projection_mean=projection.projection_mean,
                line=payload.line,
                stat_category=payload.stat_category,
                dist_type=DistributionType.NEGATIVE_BINOMIAL,
            )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"This prop could not be evaluated: {exc}") from exc

    is_over = payload.side in {"over", "yes"}
    model_probability = distribution.conditional_prob_over if is_over else distribution.conditional_prob_under
    fair_decimal = distribution.fair_decimal_over if is_over else distribution.fair_decimal_under
    fair_american = EVEngine.decimal_to_american(fair_decimal)

    settings = cache.get_settings()
    kelly_config = KellyConfig(
        bankroll=settings.bankroll,
        fraction=settings.kelly_fraction,
        w_market=0.0,
        w_model=1.0,
        min_stake=settings.min_stake,
    )
    ev_result = EVEngine.calculate(
        decimal_odds=odds_value.decimal,
        model_fair_prob=model_probability,
        prob_push=distribution.prob_push,
        config=kelly_config,
    )

    suggested_stake = ev_result.recommended_stake
    entered_stake_ev = None
    if payload.stake is not None:
        entered_stake_ev = round(payload.stake * (ev_result.blended_ev / 100.0), 2)

    side_label = "Yes" if payload.side == "yes" else payload.side.title()
    return {
        "success": True,
        "evidence": {
            "label": "Model Edge" if ev_result.blended_ev > 0 else "Model Estimate",
            "code": "model_only",
            "description": "Based on the loaded projection and distribution model. It is not an exact sharp-market comparison.",
        },
        "prop": {
            "player_name": projection.canonical_name or projection.player_name,
            "team": projection.team,
            "opponent": projection.opponent,
            "position": projection.position,
            "market": payload.stat_category.value,
            "side": payload.side,
            "side_label": side_label,
            "line": payload.line,
            "bet365_american": odds_value.american,
            "bet365_decimal": odds_value.decimal,
        },
        "projection": {
            "mean": projection.projection_mean,
            "source": projection.source,
            "updated_at": projection.updated_at,
        },
        "model": {
            "win_probability": round(model_probability, 4),
            "push_probability": round(distribution.prob_push, 4),
            "fair_decimal": round(fair_decimal, 4),
            "fair_american": fair_american,
            "distribution": distribution.distribution_type.value,
        },
        "value": {
            "expected_value_pct": ev_result.blended_ev,
            "estimated_profit_per_100": round(ev_result.blended_ev, 2),
            "is_positive": ev_result.is_positive_ev,
            "suggested_stake": suggested_stake,
            "quarter_kelly_stake": ev_result.quarter_kelly_stake,
            "half_kelly_stake": ev_result.half_kelly_stake,
            "entered_stake": payload.stake,
            "entered_stake_expected_profit": entered_stake_ev,
        },
        "warnings": [
            "Model estimates can be wrong. Confirm the exact Bet365 player, market, side, line, and odds before betting.",
            "No sharp-book comparison was used for this result.",
        ],
    }


@router.get("/tracker/bets")
def list_tracked_bets() -> dict[str, Any]:
    """Return locally stored straight bets and their cash-aware summary."""
    return {"bets": bet_tracker_store.list(), "summary": bet_tracker_store.summary()}


@router.post("/tracker/bets")
def create_tracked_bet(payload: TrackedBetCreateRequest) -> dict[str, Any]:
    """Save an already-evaluated straight prop; this never places a bet."""
    source_context = payload.source_context
    if not source_context:
        library = projection_snapshot_store.list_summaries()
        source_context = next((snapshot for snapshot in library["snapshots"] if snapshot["active"]), None)
    bet = bet_tracker_store.create({**payload.model_dump(), "source_context": source_context})
    return {"success": True, "bet": bet, "summary": bet_tracker_store.summary()}


@router.put("/tracker/bets/{bet_id}")
def update_tracked_bet(bet_id: str, payload: TrackedBetUpdateRequest) -> dict[str, Any]:
    changes = payload.model_dump(exclude_unset=True)
    if not changes:
        raise HTTPException(status_code=400, detail="Choose at least one value to update.")
    try:
        bet = bet_tracker_store.update(bet_id, changes)
    except TrackedBetNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Tracked bet not found.") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"success": True, "bet": bet, "summary": bet_tracker_store.summary()}


@router.post("/tracker/bets/{bet_id}/settle")
def settle_tracked_bet(bet_id: str, payload: TrackedBetSettleRequest) -> dict[str, Any]:
    try:
        bet = bet_tracker_store.settle(bet_id, payload.status, payload.settlement_amount)
    except TrackedBetNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Tracked bet not found.") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"success": True, "bet": bet, "summary": bet_tracker_store.summary()}


@router.post("/settings")
async def update_settings(payload: SettingsUpdateRequest) -> dict[str, Any]:
    updated = cache.set_settings(**payload.model_dump(exclude_unset=True))
    try:
        settings_store.save(updated.to_storage_dict())
    except OSError as exc:
        logger.error("Could not persist settings: %s", exc)
        raise HTTPException(status_code=500, detail="Settings could not be saved on this computer.") from exc
    cfg = updated

    fetched_events = 0
    fetch_error: str | None = None

    # If an API key was provided, immediately trigger a live odds fetch
    if payload.odds_api_key and payload.odds_api_key.strip():
        try:
            adapter = OddsPapiAdapter(
                api_key=cfg.odds_api_key,
                odds_format="decimal",
                mock_fallback=False,
                raw_snapshot_store=raw_odds_snapshot_store,
            )
            events = await adapter.fetch_odds()
            if events:
                cache.store_events(events)
                fetched_events = len(events)
                logger.info("Live fetch via API key: %d events loaded", fetched_events)
            else:
                logger.warning("Live fetch returned 0 events (key may be invalid or off-season)")
                fetch_error = "OddsPapi returned 0 NFL events — markets may not be posted yet."
        except Exception as e:
            logger.error("Live odds fetch failed: %s", e)
            fetch_error = str(e)

    if fetched_events:
        persist_loaded_data()

    # Recalculate EV with updated settings + any newly fetched data
    opps = pipeline_service.process_data()

    return {
        "success": True,
        "settings": updated.to_dict(),
        "live_fetch": {
            "triggered": bool(payload.odds_api_key and payload.odds_api_key.strip()),
            "events_fetched": fetched_events,
            "opportunities_recalculated": len(opps),
            "error": fetch_error,
        },
    }


@router.post("/fetch-live-odds")
async def fetch_live_odds() -> dict[str, Any]:
    """Manually trigger a live odds fetch using the stored API key."""
    cfg = cache.get_settings()
    if not cfg.odds_api_key or not cfg.odds_api_key.strip():
        raise HTTPException(
            status_code=400,
            detail="No API key configured. Add your OddsPapi key in Settings first.",
        )
    try:
        adapter = OddsPapiAdapter(
            api_key=cfg.odds_api_key,
            odds_format="decimal",
            mock_fallback=False,
            raw_snapshot_store=raw_odds_snapshot_store,
        )
        events = await adapter.fetch_odds()
    except Exception as e:
        logger.error("Live fetch failed: %s", e)
        raise HTTPException(status_code=502, detail=f"Live fetch failed: {e}")

    cache.store_events(events)
    persist_loaded_data()
    opps = pipeline_service.process_data()
    return {
        "success": True,
        "events_fetched": len(events),
        "opportunities_recalculated": len(opps),
        "remaining_requests": adapter.remaining_requests,
        "used_requests": adapter.used_requests,
        "diagnostic_snapshot": getattr(adapter, "last_raw_snapshot_path", None),
    }


@router.get("/opportunities")
def get_opportunities(
    min_ev: float = Query(0.0, description="Minimum blended EV percentage threshold"),
    market: str = Query("all", description="Market filter (e.g. player_pass_yds, h2h, all)"),
    search: str = Query("", description="Player or team search query"),
    bookmaker: str = Query("all", description="Bookmaker filter"),
    sort_by: str = Query("blended_ev", description="Field to sort by (blended_ev, stake, odds, player)"),
    sort_desc: bool = Query(True, description="Sort descending"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> dict[str, Any]:
    items, total = cache.get_opportunities(
        min_ev=min_ev,
        market_category=market if market != "all" else None,
        search_query=search,
        bookmaker=bookmaker if bookmaker != "all" else None,
        sort_by=sort_by,
        sort_desc=sort_desc,
        limit=limit,
        offset=offset,
    )
    return {
        "total": total,
        "count": len(items),
        "limit": limit,
        "offset": offset,
        "opportunities": [item.model_dump() for item in items],
    }


@router.get("/opportunities/{opportunity_id}")
def get_opportunity_breakdown(opportunity_id: str) -> dict[str, Any]:
    breakdown = pipeline_service.get_breakdown(opportunity_id)
    if not breakdown:
        raise HTTPException(status_code=404, detail="Opportunity not found")
    return breakdown.model_dump()


@router.get("/stats")
def get_dashboard_stats() -> dict[str, Any]:
    opps, total = cache.get_opportunities(min_ev=-100.0, limit=1000)
    positive_opps = [o for o in opps if o.blended_ev > 0]
    quarantined_opps = [o for o in positive_opps if o.is_quarantined]
    actionable_opps = [o for o in positive_opps if not o.is_quarantined]
    avg_ev = sum(o.blended_ev for o in actionable_opps) / len(actionable_opps) if actionable_opps else 0.0
    top_edge = max((o.blended_ev for o in actionable_opps), default=0.0)
    total_rec_stake = sum(o.recommended_stake for o in actionable_opps)

    return {
        "total_opportunities": total,
        "positive_ev_count": len(actionable_opps),
        "quarantined_count": len(quarantined_opps),
        "average_edge_pct": round(avg_ev, 2),
        "max_edge_pct": round(top_edge, 2),
        "total_recommended_stake": round(total_rec_stake, 2),
    }


@router.post("/upload/projections")
async def upload_projections(
    file: UploadFile | None = File(None),
    season: int = Form(2026),
    week: int = Form(1),
    label: str | None = Form(None),
) -> dict[str, Any]:
    if not file:
        raise HTTPException(status_code=400, detail="No file provided")
    
    content = await file.read()
    adapter = FantasyPointsAdapter()
    projections = adapter.parse_projections(
        content,
        filename=file.filename or "projection-import.csv",
        season=season,
        week=week,
    )
    stored = _save_projection_import(
        projections,
        label=label,
        source=file.filename or "Projection file import",
        season=season,
        week=week,
    )
    return {
        "success": True,
        "message": f"Imported {stored['count']} projections for NFL {season} Week {week}.",
        **stored,
    }


@router.post("/upload/odds")
async def upload_odds(
    file: UploadFile | None = File(None),
) -> dict[str, Any]:
    if not file:
        raise HTTPException(status_code=400, detail="No file provided")

    content = await file.read()
    text = content.decode("utf-8", errors="replace")

    adapter = CSVOddsAdapter()
    try:
        events = adapter.parse_payload(text)
    except Exception as e:
        logger.error("Failed parsing odds upload: %s", e)
        raise HTTPException(status_code=400, detail=f"Error parsing odds file: {str(e)}")

    cache.store_events(events)
    persist_loaded_data()
    # Recalculate pipeline
    opps = pipeline_service.process_data()

    return {
        "success": True,
        "message": f"Successfully ingested {len(events)} games/events. Found {len(opps)} +EV opportunities.",
        "events_count": len(events),
        "opportunities_count": len(opps),
    }


@router.post("/upload/paste")
def paste_data(payload: PasteUploadRequest) -> dict[str, Any]:
    if not payload.content.strip():
        raise HTTPException(status_code=400, detail="Pasted content is empty")

    if payload.data_type == "projections":
        adapter = FantasyPointsAdapter()
        projections = adapter.parse_projections(payload.content, season=payload.season, week=payload.week)
        stored = _save_projection_import(
            projections,
            label=payload.label,
            source="Pasted projection text",
            season=payload.season,
            week=payload.week,
        )
        return {
            "success": True,
            "message": f"Imported {stored['count']} pasted projections for NFL {payload.season} Week {payload.week}.",
            **stored,
        }
    else:
        adapter = CSVOddsAdapter()
        events = adapter.parse_payload(payload.content)
        cache.store_events(events)
        persist_loaded_data()
        opps = pipeline_service.process_data()
        return {
            "success": True,
            "message": f"Parsed {len(events)} games/events from clipboard.",
            "count": len(events),
            "opportunities": len(opps),
        }


@router.post("/recalculate")
def trigger_recalculate() -> dict[str, Any]:
    opps = pipeline_service.process_data()
    return {
        "success": True,
        "message": f"Pipeline recalculated with {len(opps)} opportunities.",
        "count": len(opps),
    }


@router.post("/reset")
def reset_all_data() -> dict[str, Any]:
    """
    Clear all in-memory and persisted odds, player projections, and calculated opportunities.
    """
    cache.store_events([])
    cache.replace_projections([])
    cache.store_opportunities([])
    persist_loaded_data()
    return {
        "success": True,
        "message": "All odds, projections, and calculated +EV opportunities have been reset.",
        "count": 0,
    }



class BrowserPropItem(BaseModel):
    player: str
    team: str | None = None
    market: str = "player_pass_yds"
    line: float | None = None
    over_odds: float | int | str | None = None
    under_odds: float | int | str | None = None
    price: float | int | str | None = None
    game: str | None = None
    opponent: str | None = None
    commence_time: datetime | str | None = None


class BrowserIngestPayload(BaseModel):
    bookmaker: str = "bet365"
    sport: str = "americanfootball_nfl"
    props: list[BrowserPropItem] = []
    raw_text: str | None = None
    append: bool = True


def _parse_odds_val(val: Any) -> OddsValue | None:
    if val is None:
        return None
    try:
        if isinstance(val, (int, float)):
            if abs(val) >= 100 or (isinstance(val, int) and val != 0):
                return OddsValue.from_american(int(val))
            elif val > 1.0:
                return OddsValue.from_decimal(float(val))
        elif isinstance(val, str):
            cleaned = val.strip().replace("$", "").replace("x", "")
            if not cleaned or cleaned in ("-", "--", "N/A", "n/a"):
                return None
            if cleaned.startswith("+") or cleaned.startswith("-"):
                return OddsValue.from_american(int(float(cleaned)))
            num = float(cleaned)
            if num >= 100 or num <= -100:
                return OddsValue.from_american(int(num))
            elif num > 1.0:
                return OddsValue.from_decimal(num)
    except Exception as e:
        logger.debug("Could not parse odds value %r: %s", val, e)
    return None


@router.post("/ingest/bet365")
@router.post("/ingest")
def ingest_browser_props(payload: BrowserIngestPayload) -> dict[str, Any]:
    """
    Direct ingestion endpoint for Bet365 / browser userscript / extension.
    Accepts normalized or raw props extracted from live browser DOM or WebSocket streams.
    """
    import re

    if payload.raw_text and not payload.props:
        adapter = CSVOddsAdapter()
        events = adapter.parse_payload(payload.raw_text)
        if payload.append:
            existing = cache.get_events()
            events = _merge_events(existing, events, bookmaker_key=payload.bookmaker)
        cache.store_events(events)
        persist_loaded_data()
        opps = pipeline_service.process_data()
        return {
            "success": True,
            "message": f"Successfully ingested {len(events)} events from raw text.",
            "props_count": sum(len(m.outcomes) for e in events for b in e.bookmakers for m in b.markets),
            "opportunities_count": len(opps),
        }

    if not payload.props:
        raise HTTPException(status_code=400, detail="No props or raw_text provided in payload")

    # Group props by game/matchup
    grouped_props: dict[str, list[BrowserPropItem]] = {}
    for item in payload.props:
        if not item.player or not item.player.strip():
            continue
        game_key = (item.game or "NFL Slate").strip()
        grouped_props.setdefault(game_key, []).append(item)

    bookmaker_key = payload.bookmaker.lower().strip() or "bet365"
    bookmaker_title = "Bet365" if bookmaker_key == "bet365" else bookmaker_key.title()

    new_events: list[Event] = []
    total_market_count = 0

    for game_name, prop_items in grouped_props.items():
        home_team = "NFL Home"
        away_team = "NFL Away"
        if "@" in game_name:
            parts = game_name.split("@")
            away_team = TeamNormalizer.canonical_team(parts[0].strip())
            home_team = TeamNormalizer.canonical_team(parts[1].strip())
        elif "vs" in game_name.lower():
            parts = re.split(r"\s+vs\.?\s+", game_name, flags=re.IGNORECASE)
            if len(parts) == 2:
                home_team = TeamNormalizer.canonical_team(parts[0].strip())
                away_team = TeamNormalizer.canonical_team(parts[1].strip())


        market_offers: list[MarketOffer] = []

        for p in prop_items:
            raw_m = p.market.lower().strip()
            market_key = CSVOddsAdapter.MARKET_MAPPINGS.get(raw_m, raw_m)
            clean_name = PlayerNameNormalizer.clean_name(p.player)
            line_val = p.line

            outcomes: list[MarketOutcome] = []

            over_odds = _parse_odds_val(p.over_odds)
            under_odds = _parse_odds_val(p.under_odds)

            if over_odds and under_odds:
                outcomes.append(
                    MarketOutcome(
                        name=f"{p.player} Over",
                        point=line_val,
                        odds=over_odds,
                        player_name=p.player,
                        player_canonical=clean_name,
                        outcome_type=OutcomeType.OVER,
                    )
                )
                outcomes.append(
                    MarketOutcome(
                        name=f"{p.player} Under",
                        point=line_val,
                        odds=under_odds,
                        player_name=p.player,
                        player_canonical=clean_name,
                        outcome_type=OutcomeType.UNDER,
                    )
                )
            elif p.price is not None:
                price_odds = _parse_odds_val(p.price)
                if price_odds:
                    outcomes.append(
                        MarketOutcome(
                            name=p.player,
                            point=line_val,
                            odds=price_odds,
                            player_name=p.player,
                            player_canonical=clean_name,
                            outcome_type=OutcomeType.YES if "td" in market_key else OutcomeType.OVER,
                        )
                    )

            if outcomes:
                offer = MarketOffer(
                    market_key=market_key,
                    label=f"{p.player} - {p.market}",
                    player_name=p.player,
                    player_canonical=clean_name,
                    point=line_val,
                    outcomes=outcomes,
                    bookmaker=bookmaker_key,
                    timestamp=datetime.now(timezone.utc),
                )
                market_offers.append(offer)

        if market_offers:
            total_market_count += len(market_offers)
            event_id = f"{bookmaker_key}_{game_name.replace(' ', '_').replace('@', 'at')}_{datetime.now(timezone.utc).strftime('%Y%m%d')}"
            bookmaker_obj = Bookmaker(
                key=bookmaker_key,
                title=bookmaker_title,
                markets=market_offers,
                last_update=datetime.now(timezone.utc),
            )
            ev = Event(
                id=event_id,
                sport_key="americanfootball_nfl",
                sport_title="NFL",
                home_team=home_team,
                away_team=away_team,
                commence_time=datetime.now(timezone.utc),
                bookmakers=[bookmaker_obj],
            )
            new_events.append(ev)

    if not new_events:
        raise HTTPException(status_code=400, detail="Could not parse any valid prop markets with valid odds.")

    if payload.append:
        existing_events = cache.get_events()
        final_events = _merge_events(existing_events, new_events, bookmaker_key=bookmaker_key)
    else:
        final_events = new_events

    cache.store_events(final_events)
    persist_loaded_data()
    opps = pipeline_service.process_data()

    return {
        "success": True,
        "message": f"Successfully ingested {len(payload.props)} {bookmaker_title} props across {len(new_events)} event groups.",
        "props_ingested": len(payload.props),
        "markets_created": total_market_count,
        "events_count": len(final_events),
        "opportunities_count": len(opps),
    }


def _merge_events(existing: list[Event], incoming: list[Event], bookmaker_key: str = "bet365") -> list[Event]:
    event_map: dict[str, Event] = {e.id: e for e in existing}
    for inc in incoming:
        matched = False
        for ex in event_map.values():
            if (ex.home_team == inc.home_team and ex.away_team == inc.away_team) or ex.id == inc.id:
                inc_bm = inc.get_bookmaker(bookmaker_key)
                if not inc_bm:
                    continue
                bm_found = False
                for bm in ex.bookmakers:
                    if bm.key == bookmaker_key:
                        incoming_player_keys = {
                            (m.market_key, m.player_canonical)
                            for m in inc_bm.markets if m.player_canonical
                        }
                        filtered_markets = [
                            m for m in bm.markets
                            if (m.market_key, m.player_canonical) not in incoming_player_keys
                        ]
                        incoming_players = {m.player_canonical for m in inc_bm.markets if m.player_canonical}
                        for fm in filtered_markets:
                            if not fm.player_canonical and fm.outcomes:
                                fm.outcomes = [
                                    o for o in fm.outcomes
                                    if o.player_canonical not in incoming_players
                                ]
                        filtered_markets = [fm for fm in filtered_markets if fm.outcomes]
                        bm.markets = filtered_markets + inc_bm.markets
                        bm_found = True
                        break
                if not bm_found:
                    ex.bookmakers.append(inc_bm)
                matched = True
                break
        if not matched:
            event_map[inc.id] = inc

    return list(event_map.values())
