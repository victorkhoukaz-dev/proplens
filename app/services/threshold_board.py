"""Projection-only threshold calculations for the manual Bet365 workflow."""
from __future__ import annotations

from typing import Any

from app.core.distributions import DistributionEngine, DistributionType
from app.core.ev import EVEngine
from app.schemas.projections import PlayerProjection, Position, StatCategory


THRESHOLD_MARKETS: tuple[StatCategory, ...] = (
    StatCategory.PASSING_YARDS,
    StatCategory.PASSING_TDS,
    StatCategory.PASSING_INTERCEPTIONS,
    StatCategory.RUSHING_YARDS,
    StatCategory.RECEIVING_YARDS,
    StatCategory.RECEPTIONS,
)

ANYTIME_TD_MARKET = StatCategory.ANYTIME_TD


def _distribution(projection: PlayerProjection, line: float):
    if projection.stat_category.is_continuous:
        position = Position(projection.position) if projection.position in Position._value2member_map_ else Position.WR
        return DistributionEngine.evaluate_continuous_prop(
            projection_mean=projection.projection_mean,
            line=line,
            position=position,
            stat_category=projection.stat_category,
            dist_type=DistributionType.LOG_NORMAL,
            cv_override=projection.projection_std,
        )
    return DistributionEngine.evaluate_discrete_prop(
        projection_mean=projection.projection_mean,
        line=line,
        stat_category=projection.stat_category,
        dist_type=DistributionType.NEGATIVE_BINOMIAL,
    )


def _is_positive(distribution: Any, side: str, decimal_odds: float) -> bool:
    probability = distribution.conditional_prob_over if side == "over" else distribution.conditional_prob_under
    return EVEngine.calculate_single_ev(probability, decimal_odds, distribution.prob_push) > 0


def _half_point_lines(maximum: float) -> list[float]:
    return [round(step + 0.5, 1) for step in range(0, int(maximum) + 1)]


def thresholds_for_projection(projection: PlayerProjection, decimal_odds: float) -> dict[str, Any]:
    """Return the positive-EV boundary lines using the evaluator's exact model.

    Lines deliberately use sportsbook-style half points, avoiding ambiguous pushes.
    The board is a watchlist: it does not know the current Bet365 offer.
    """
    if projection.stat_category not in THRESHOLD_MARKETS:
        raise ValueError("This market does not have a two-sided threshold board yet.")
    if decimal_odds <= 1.0:
        raise ValueError("Assumed decimal odds must be above 1.00.")

    # A broad but bounded line range. Yardage thresholds can be high for quarterbacks;
    # discrete markets need only a small number of standard half-point alternatives.
    upper_bound = max(20.0, projection.projection_mean * (4.0 if projection.stat_category.is_continuous else 5.0))
    candidates = _half_point_lines(upper_bound)
    positive_over = []
    positive_under = []
    for line in candidates:
        distribution = _distribution(projection, line)
        if _is_positive(distribution, "over", decimal_odds):
            positive_over.append(line)
        if _is_positive(distribution, "under", decimal_odds):
            positive_under.append(line)

    return {
        "player_name": projection.canonical_name or projection.player_name,
        "team": projection.team,
        "opponent": projection.opponent,
        "position": projection.position,
        "market": projection.stat_category.value,
        "projection_mean": round(projection.projection_mean, 2),
        "over_max_positive_line": max(positive_over) if positive_over else None,
        "under_min_positive_line": min(positive_under) if positive_under else None,
    }


def anytime_td_watch_for_projection(projection: PlayerProjection) -> dict[str, Any]:
    """Return the model probability and break-even price for an Anytime TD Yes bet.

    Bet365's Anytime TD market is one-sided: there is a Yes price and no
    practical No selection to scan. The fair decimal price is the boundary;
    a live price strictly above it is model-positive before rounding.
    """
    if projection.stat_category != ANYTIME_TD_MARKET:
        raise ValueError("This row is not an Anytime TD projection.")

    distribution = _distribution(projection, 0.5)
    return {
        "player_name": projection.canonical_name or projection.player_name,
        "team": projection.team,
        "opponent": projection.opponent,
        "position": projection.position,
        "market": projection.stat_category.value,
        "projection_mean": round(projection.projection_mean, 2),
        "model_probability": distribution.conditional_prob_over,
        "minimum_decimal_odds": distribution.fair_decimal_over,
    }
