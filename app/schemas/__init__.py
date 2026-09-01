"""
app.schemas: Pydantic v2 domain schemas for odds, projections, and EV calculations.
"""

from app.schemas.odds import (
    Bookmaker,
    Event,
    MarketOffer,
    MarketOutcome,
    MarketType,
    OddsValue,
    OutcomeType,
    american_to_decimal,
    decimal_to_american,
)
from app.schemas.projections import (
    PlayerProjection,
    Position,
    StatCategory,
)
from app.schemas.ev import (
    EVResult,
    MatchedEVOpportunity,
    PropBreakdown,
)

__all__ = [
    # Odds
    "OutcomeType",
    "MarketType",
    "american_to_decimal",
    "decimal_to_american",
    "OddsValue",
    "MarketOutcome",
    "MarketOffer",
    "Bookmaker",
    "Event",
    # Projections
    "StatCategory",
    "Position",
    "PlayerProjection",
    # EV
    "EVResult",
    "MatchedEVOpportunity",
    "PropBreakdown",
]
