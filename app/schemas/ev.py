"""
Pydantic v2 schemas for Expected Value (EV) opportunities, mathematical results, and UI breakdown modals.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.odds import OutcomeType
from app.schemas.projections import StatCategory


class EVResult(BaseModel):
    """
    Pure mathematical container for EV calculations and Fractional Kelly bet sizing.
    """
    model_config = ConfigDict(populate_by_name=True, from_attributes=True)

    market_implied_ev: float | None = Field(
        default=None,
        description="EV against sharp devigged benchmark: (P_mkt * Decimal) - (1 - P_push)"
    )
    model_implied_ev: float | None = Field(
        default=None,
        description="EV against statistical projection distribution: (P_mdl * Decimal) - (1 - P_push)"
    )
    blended_ev: float = Field(
        ...,
        description="Weighted consensus EV: w_mkt * EV_mkt + w_mdl * EV_mdl"
    )
    blended_win_prob: float = Field(
        ...,
        description="Weighted win probability: w_mkt * P_mkt + w_mdl * P_mdl"
    )
    prob_push: float = Field(
        default=0.0,
        description="Push refund probability for integer lines"
    )
    quarter_kelly_fraction: float = Field(
        ...,
        description="Quarter Kelly fraction: 0.25 * [ (P_win * D - (1 - P_push)) / (D - 1) ]"
    )
    quarter_kelly_stake: float = Field(
        ...,
        description="Recommended stake for Quarter Kelly based on bankroll and safety caps"
    )
    half_kelly_stake: float = Field(
        ...,
        description="Stake for Half Kelly sizing"
    )
    full_kelly_stake: float = Field(
        ...,
        description="Stake for Full Kelly sizing"
    )
    recommended_stake: float = Field(
        ...,
        description="Selected actionable stake (defaults to Quarter Kelly)"
    )
    is_capped: bool = Field(
        default=False,
        description="True if recommended stake was truncated by allocation cap"
    )
    bankroll: float = Field(
        default=1000.0,
        description="Bankroll used for stake calculations"
    )

    @property
    def edge_pct(self) -> float:
        """Alias for blended_ev percentage."""
        return self.blended_ev

    @property
    def is_positive_ev(self) -> bool:
        """True if the blended consensus EV is strictly positive."""
        return self.blended_ev > 0.0

    @property
    def ev_decimal(self) -> float:
        """Blended EV expressed as decimal fraction (e.g. 0.0525 for 5.25%)."""
        return round(self.blended_ev / 100.0, 6)

    @property
    def full_kelly_fraction(self) -> float:
        """Full Kelly bankroll fraction."""
        return round(self.quarter_kelly_fraction * 4.0, 6) if self.quarter_kelly_fraction > 0 else 0.0

    @property
    def half_kelly_fraction(self) -> float:
        """Half Kelly bankroll fraction."""
        return round(self.quarter_kelly_fraction * 2.0, 6) if self.quarter_kelly_fraction > 0 else 0.0

    @property
    def eighth_kelly_fraction(self) -> float:
        """Eighth Kelly bankroll fraction."""
        return round(self.quarter_kelly_fraction * 0.5, 6) if self.quarter_kelly_fraction > 0 else 0.0

    @property
    def eighth_kelly_stake(self) -> float:
        """Actionable Eighth Kelly stake."""
        if self.quarter_kelly_fraction <= 0.0 or self.bankroll <= 0.0:
            return 0.0
        raw = self.bankroll * self.eighth_kelly_fraction
        return round(raw, 2)

    def to_dict(self) -> dict[str, Any]:
        """Serialize result to dictionary."""
        return self.model_dump()


class MatchedEVOpportunity(BaseModel):
    """
    Represents a unified, actionable +EV betting opportunity displayed in the web dashboard table.
    """
    model_config = ConfigDict(populate_by_name=True, from_attributes=True)

    id: str = Field(..., description="Unique deterministic opportunity ID hash")
    event_id: str = Field(..., description="Parent event ID")
    game: str = Field(..., description="Formatted match string (e.g. 'KC @ BUF')")
    commence_time: datetime = Field(..., description="Kickoff time in UTC")
    sport_key: str = Field(default="americanfootball_nfl", description="Sport key")

    # Player / Entity Metadata
    player_name: str | None = Field(default=None, description="Player name (None for game-level markets)")
    canonical_name: str | None = Field(default=None, description="Normalized canonical player name")
    team: str | None = Field(default=None, description="Canonical team abbreviation (e.g. 'KC')")
    position: str | None = Field(default=None, description="Player position (e.g. 'QB', 'WR')")

    # Market Definition
    market_key: str = Field(..., description="Market key (e.g. 'player_pass_yds', 'h2h')")
    market_label: str = Field(..., description="Display label (e.g. 'Passing Yards', 'Moneyline')")
    stat_category: StatCategory | None = Field(default=None, description="Stat category enum if player prop")
    line: float | None = Field(default=None, description="Line/Point value (e.g. 275.5, -3.5)")
    outcome_name: str = Field(..., description="Outcome name (e.g. 'Over', 'Under', 'KC')")
    outcome_type: OutcomeType | str = Field(..., description="Outcome type classification ('over', 'under', etc.)")

    # Target Sportsbook (Bet365 Canada)
    target_book: str = Field(default="bet365", description="Target execution sportsbook")
    target_american: int = Field(..., description="Bet365 American odds (e.g. -110)")
    target_decimal: float = Field(..., description="Bet365 Decimal odds (e.g. 1.909091)")

    # Benchmark Sportsbook (Pinnacle / Circa)
    benchmark_book: str = Field(default="pinnacle", description="Sharp benchmark bookmaker")
    benchmark_american: int | None = Field(default=None, description="Benchmark American odds")
    benchmark_decimal: float | None = Field(default=None, description="Benchmark Decimal odds")

    # Fair Probabilities & Devigged Fair Odds
    market_fair_prob: float | None = Field(default=None, description="Vig-free market win probability from benchmark")
    market_fair_decimal: float | None = Field(default=None, description="Vig-free benchmark fair decimal odds")
    market_fair_american: int | None = Field(default=None, description="Vig-free benchmark fair American odds")

    model_fair_prob: float | None = Field(default=None, description="Model win probability from projection distribution")
    model_fair_decimal: float | None = Field(default=None, description="Model fair decimal odds")
    model_fair_american: int | None = Field(default=None, description="Model fair American odds")

    blended_win_prob: float = Field(..., description="Weighted blended consensus win probability")
    prob_push: float = Field(default=0.0, description="Push probability on integer lines")

    # Expected Value Metrics
    market_ev: float | None = Field(default=None, description="Market-implied EV decimal (e.g. 0.045 = +4.5%)")
    model_ev: float | None = Field(default=None, description="Model-implied EV decimal (e.g. 0.072 = +7.2%)")
    blended_ev: float = Field(..., description="Blended consensus EV decimal (e.g. 0.056 = +5.6%)")
    edge_pct: float = Field(..., description="Blended EV expressed as percentage (e.g. 5.60)")

    # Kelly Sizing Recommendations
    quarter_kelly: float = Field(..., description="Quarter Kelly bankroll fraction")
    half_kelly: float = Field(..., description="Half Kelly bankroll fraction")
    full_kelly: float = Field(..., description="Full Kelly bankroll fraction")
    quarter_kelly_stake: float = Field(..., description="Actionable Quarter Kelly dollar stake")
    half_kelly_stake: float = Field(..., description="Half Kelly dollar stake")
    full_kelly_stake: float = Field(..., description="Full Kelly dollar stake")
    recommended_stake: float = Field(..., description="Recommended dollar stake")

    # Status & Tags
    is_positive_ev: bool = Field(default=True, description="True if blended_ev > 0")
    is_quarantined: bool = Field(
        default=False,
        description="True when the calculated edge requires source-market verification before action",
    )
    quarantine_reason: str | None = Field(
        default=None,
        description="Human-readable reason the opportunity is not actionable",
    )
    tags: list[str] = Field(default_factory=list, description="Visual badge tags (e.g. ['High Edge', 'Dual Signal'])")
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Timestamp when opportunity was generated"
    )


class PropBreakdown(BaseModel):
    """
    Comprehensive payload for the UI Prop Breakdown modal / drawer.
    Encompasses raw quotes, devigging parameters, distribution curve coordinates, and calculation steps.
    """
    model_config = ConfigDict(populate_by_name=True, from_attributes=True)

    opportunity: MatchedEVOpportunity = Field(..., description="Parent +EV opportunity")

    # Multi-Book Odds Comparison
    odds_comparison: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Comparison table across all books (Bet365, Pinnacle, Circa, DraftKings, FanDuel)"
    )

    # Devigging Audit
    devig_summary: dict[str, Any] = Field(
        default_factory=dict,
        description="Devigging details (method: Shin/Multiplicative, benchmark overround, unrounded fair odds, z parameter)"
    )

    # Statistical Distribution Audit
    distribution_summary: dict[str, Any] | None = Field(
        default=None,
        description="Distribution parameters (distribution_type, mean, CV/alpha, P(Over), P(Under), P(Push))"
    )

    # Chart.js Probability Density Curve Coordinates
    chart_coordinates: dict[str, Any] | None = Field(
        default=None,
        description="Chart.js dataset: x-axis points, y-axis density values, fill coordinates, vertical line markers"
    )

    # Step-by-Step Educational Calculation Steps
    ev_math_steps: list[dict[str, str]] = Field(
        default_factory=list,
        description="Step-by-step breakdown explaining formulas and numerical values used"
    )
