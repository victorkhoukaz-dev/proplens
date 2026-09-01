"""
Pydantic v2 schemas for odds conversion, market outcomes, market offers, bookmakers, and events.
"""
from __future__ import annotations

import math
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    computed_field,
    field_validator,
    model_validator,
)


class OutcomeType(str, Enum):
    """Standardized market outcome types."""
    OVER = "over"
    UNDER = "under"
    YES = "yes"
    NO = "no"
    HOME = "home"
    AWAY = "away"
    DRAW = "draw"


class MarketType(str, Enum):
    """Standardized NFL market keys."""
    # Player Props
    PLAYER_PASS_YDS = "player_pass_yds"
    PLAYER_PASS_TDS = "player_pass_tds"
    PLAYER_PASS_INTERCEPTIONS = "player_pass_interceptions"
    PLAYER_PASS_ATTEMPTS = "player_pass_attempts"
    PLAYER_PASS_COMPLETIONS = "player_pass_completions"
    PLAYER_RUSH_YDS = "player_rush_yds"
    PLAYER_RUSH_ATTEMPTS = "player_rush_attempts"
    PLAYER_RUSH_TDS = "player_rush_tds"
    PLAYER_REC_YDS = "player_rec_yds"
    PLAYER_RECEPTIONS = "player_receptions"
    PLAYER_ANYTIME_TD = "player_anytime_td"
    PLAYER_FIELD_GOALS = "player_field_goals"
    PLAYER_SACKS = "player_sacks"
    PLAYER_TACKLES_ASSISTS = "player_tackles_assists"

    # Core Game Lines
    H2H = "h2h"                    # Moneyline
    SPREADS = "spreads"            # Point Spread
    TOTALS = "totals"              # Game Total Points


def american_to_decimal(american: int) -> float:
    """
    Convert American odds (int) to Decimal odds (float).

    Formulas:
    - Positive odds (+A): Decimal = 1.0 + (A / 100.0)
    - Negative odds (-A): Decimal = 1.0 + (100.0 / |A|)
    - Even money (+100 or -100): Decimal = 2.0

    Raises:
        ValueError: If American odds fall strictly between -100 and +100.
    """
    if -100 < american < 100:
        raise ValueError(
            f"Invalid American odds '{american}'. American odds cannot be between -100 and +100."
        )
    if american >= 100:
        return round(1.0 + (american / 100.0), 6)
    else:
        return round(1.0 + (100.0 / abs(american)), 6)


def decimal_to_american(decimal: float) -> int:
    """
    Convert Decimal odds (float) to American odds (int).

    Formulas:
    - Decimal >= 2.0: American = round((Decimal - 1.0) * 100)
    - 1.0 < Decimal < 2.0: American = -round(100.0 / (Decimal - 1.0))

    Raises:
        ValueError: If Decimal odds <= 1.0.
    """
    if decimal <= 1.0:
        raise ValueError(
            f"Invalid Decimal odds '{decimal}'. Decimal odds must be strictly greater than 1.0."
        )
    if decimal >= 2.0:
        return int(round((decimal - 1.0) * 100.0))
    else:
        denom = decimal - 1.0
        if denom <= 0.0:
            raise ValueError(f"Invalid Decimal odds '{decimal}'.")
        return -int(round(100.0 / denom))


class OddsValue(BaseModel):
    """
    Immutable representation of betting odds supporting bidirectional American
    and Decimal representation and automated implied probability calculation.
    """
    model_config = ConfigDict(frozen=True, populate_by_name=True)

    american: int = Field(
        ...,
        description="American odds integer (e.g. -110, +150, -10000, +99900). Cannot be in range (-100, +100).",
    )
    decimal: float = Field(
        ...,
        description="Decimal odds float (e.g. 1.909091, 2.50, 1.01, 1000.0). Must be > 1.0.",
    )

    @model_validator(mode="before")
    @classmethod
    def sync_and_validate_odds(cls, data: Any) -> Any:
        """
        Validate and synchronize American and Decimal odds.
        Accepts dict with 'american', 'decimal', or both.
        """
        if not isinstance(data, dict):
            return data

        # Make a copy so we don't mutate input unexpectedly
        data = dict(data)
        american = data.get("american")
        decimal = data.get("decimal")

        if american is None and decimal is None:
            raise ValueError("Must provide at least 'american' or 'decimal' odds.")

        if american is not None and decimal is None:
            if not isinstance(american, int):
                try:
                    american = int(american)
                except (ValueError, TypeError) as e:
                    raise ValueError(f"Invalid American odds: {american}") from e
            calc_decimal = american_to_decimal(american)
            data["american"] = american
            data["decimal"] = calc_decimal
            return data

        if decimal is not None and american is None:
            if not isinstance(decimal, (int, float)):
                try:
                    decimal = float(decimal)
                except (ValueError, TypeError) as e:
                    raise ValueError(f"Invalid Decimal odds: {decimal}") from e
            calc_american = decimal_to_american(float(decimal))
            data["american"] = calc_american
            data["decimal"] = round(float(decimal), 6)
            return data

        # Both american and decimal provided -> validate consistency
        try:
            american_val = int(american)
            decimal_val = float(decimal)
        except (ValueError, TypeError) as e:
            raise ValueError(f"Invalid odds values provided: american={american}, decimal={decimal}") from e

        if -100 < american_val < 100:
            raise ValueError(
                f"Invalid American odds '{american_val}'. Cannot be in range (-100, +100)."
            )
        if decimal_val <= 1.0:
            raise ValueError(
                f"Invalid Decimal odds '{decimal_val}'. Must be strictly > 1.0."
            )

        expected_decimal = american_to_decimal(american_val)
        # Allow tolerance of 0.025 for bookmaker rounding discrepancies
        if abs(decimal_val - expected_decimal) <= 0.025:
            decimal_val = expected_decimal

        data["american"] = american_val
        data["decimal"] = round(decimal_val, 6)
        return data

    @computed_field
    @property
    def implied_probability(self) -> float:
        """
        Compute un-devigged implied probability: P = 1.0 / Decimal.
        """
        return round(1.0 / self.decimal, 6)

    @classmethod
    def from_american(cls, american: int) -> OddsValue:
        """Factory constructor from American odds."""
        return cls(american=american)

    @classmethod
    def from_decimal(cls, decimal: float) -> OddsValue:
        """Factory constructor from Decimal odds."""
        return cls(decimal=decimal)

    @classmethod
    def from_probability(cls, prob: float) -> OddsValue:
        """Factory constructor from true/implied probability (0 < prob < 1)."""
        if not (0.0 < prob < 1.0):
            raise ValueError(f"Probability must be strictly between 0 and 1, got {prob}")
        decimal = round(1.0 / prob, 6)
        return cls.from_decimal(decimal)


class MarketOutcome(BaseModel):
    """Represents an individual wagerable outcome within a betting market."""
    model_config = ConfigDict(populate_by_name=True, from_attributes=True)

    name: str = Field(..., description="Outcome name (e.g. 'Over', 'Under', 'Kansas City Chiefs', 'Patrick Mahomes')")
    point: float | None = Field(default=None, description="Line/spread/total point (e.g. 275.5, -3.5, 48.5)")
    odds: OddsValue = Field(..., description="Wager odds in American and Decimal format")
    player_id: str | None = Field(default=None, description="External or canonical player identifier")
    player_name: str | None = Field(default=None, description="Player name associated with this outcome")
    player_canonical: str | None = Field(default=None, description="Canonical normalized player name")
    outcome_type: OutcomeType | str = Field(
        default=OutcomeType.OVER,
        description="Standardized outcome classification ('over', 'under', 'yes', 'no', 'home', 'away', 'draw')"
    )
    description: str | None = Field(default=None, description="Additional context or description")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Arbitrary provider metadata")

    @model_validator(mode="before")
    @classmethod
    def handle_odds_alias(cls, data: Any) -> Any:
        if isinstance(data, dict):
            data = dict(data)
            if "odds" not in data and "price" in data:
                data["odds"] = data.pop("price")
            # If odds is raw int or float, wrap into OddsValue
            if "odds" in data and isinstance(data["odds"], (int, float)):
                val = data["odds"]
                if isinstance(val, int) or (isinstance(val, float) and abs(val) >= 100):
                    data["odds"] = OddsValue.from_american(int(val))
                else:
                    data["odds"] = OddsValue.from_decimal(float(val))
        return data


class MarketOffer(BaseModel):
    """Represents a specific market offered by a bookmaker for an event."""
    model_config = ConfigDict(populate_by_name=True, from_attributes=True)

    market_key: str = Field(..., description="Standard market identifier (e.g. 'player_pass_yds', 'h2h', 'spreads')")
    market_type: str | None = Field(default=None, description="Category or canonical market type")
    label: str = Field(..., description="Human-readable title (e.g. 'Patrick Mahomes - Passing Yards')")
    player_name: str | None = Field(default=None, description="Player name for prop markets")
    player_canonical: str | None = Field(default=None, description="Canonical normalized player name")
    point: float | None = Field(default=None, description="Market-level line point if uniform across outcomes")
    outcomes: list[MarketOutcome] = Field(default_factory=list, description="List of wagering outcomes")
    bookmaker: str = Field(default="unknown", description="Bookmaker key (e.g. 'bet365', 'pinnacle', 'circa')")
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Timestamp when odds were retrieved or recorded"
    )
    last_update: datetime | None = Field(default=None, description="Timestamp of last odds update")
    is_live: bool = Field(default=False, description="Whether market is live in-game")

    def get_outcome(self, outcome_type: OutcomeType | str) -> MarketOutcome | None:
        """Retrieve outcome by type ('over', 'under', 'yes', 'no', 'home', 'away')."""
        target = outcome_type.value if isinstance(outcome_type, OutcomeType) else str(outcome_type).lower()
        for o in self.outcomes:
            o_type = o.outcome_type.value if isinstance(o.outcome_type, OutcomeType) else str(o.outcome_type).lower()
            if o_type == target:
                return o
        return None

    @property
    def is_two_way(self) -> bool:
        """Check if market contains exactly 2 outcomes."""
        return len(self.outcomes) == 2

    @property
    def overround(self) -> float:
        """Calculate market overround (sum of un-devigged implied probabilities)."""
        return round(sum(o.odds.implied_probability for o in self.outcomes), 6)


class Bookmaker(BaseModel):
    """Represents a sportsbook entity and its offered markets."""
    model_config = ConfigDict(populate_by_name=True, from_attributes=True)

    key: str = Field(..., description="Unique sportsbook key (e.g. 'bet365', 'pinnacle', 'circa')")
    title: str = Field(..., description="Display title (e.g. 'Bet365', 'Pinnacle', 'Circa Sports')")
    markets: list[MarketOffer] = Field(default_factory=list, description="Active market offers")
    last_update: datetime | None = Field(default=None, description="Timestamp of last update from bookmaker")

    def get_market(self, market_key: str, player_name: str | None = None) -> MarketOffer | None:
        """Find market offer by market key and optional player name."""
        for m in self.markets:
            if m.market_key == market_key:
                if player_name is None:
                    return m
                elif m.player_name and m.player_name.lower() == player_name.lower():
                    return m
                elif m.player_canonical and player_name and m.player_canonical.lower() == player_name.lower():
                    return m
        return None


class Event(BaseModel):
    """Represents a scheduled sporting event (game) with bookmaker odds."""
    model_config = ConfigDict(populate_by_name=True, from_attributes=True)

    id: str = Field(..., description="Unique event identifier")
    sport_key: str = Field(default="americanfootball_nfl", description="Sport key")
    sport_title: str = Field(default="NFL", description="Sport display title")
    commence_time: datetime = Field(..., description="Scheduled kickoff time in UTC")
    home_team: str = Field(..., description="Home team name (e.g. 'Kansas City Chiefs')")
    away_team: str = Field(..., description="Away team name (e.g. 'Buffalo Bills')")
    home_team_canonical: str | None = Field(default=None, description="Canonical 2/3 letter code (e.g. 'KC')")
    away_team_canonical: str | None = Field(default=None, description="Canonical 2/3 letter code (e.g. 'BUF')")
    bookmakers: list[Bookmaker] = Field(default_factory=list, description="List of bookmakers quoting this event")

    @property
    def game_title(self) -> str:
        """Formatted game title: 'AWAY @ HOME'."""
        away = self.away_team_canonical or self.away_team
        home = self.home_team_canonical or self.home_team
        return f"{away} @ {home}"

    def get_bookmaker(self, key: str) -> Bookmaker | None:
        """Retrieve bookmaker by key."""
        target = key.lower().strip()
        for b in self.bookmakers:
            if b.key.lower().strip() == target:
                return b
        return None
