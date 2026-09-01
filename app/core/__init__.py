"""
app.core: Core mathematical, modeling, and normalization engines.
"""

from app.core.devig import (
    DevigEngine,
    DevigMethod,
    DevigResult,
    american_to_decimal,
    calculate_overround,
    decimal_to_american,
    devig,
    devig_additive,
    devig_multiplicative,
    devig_power,
    devig_shin,
    implied_probability,
    odds_to_implied_probs,
)
from app.core.normalizer import (
    FIRST_NAME_MAP,
    NFL_CANONICAL_TEAMS,
    NFL_TEAM_LOOKUP,
    PLAYER_ALIAS_MAP,
    PlayerNameNormalizer,
    TeamNormalizer,
)

__all__ = [
    "PlayerNameNormalizer",
    "TeamNormalizer",
    "NFL_CANONICAL_TEAMS",
    "NFL_TEAM_LOOKUP",
    "FIRST_NAME_MAP",
    "PLAYER_ALIAS_MAP",
    "DevigMethod",
    "DevigResult",
    "DevigEngine",
    "devig",
    "devig_multiplicative",
    "devig_additive",
    "devig_power",
    "devig_shin",
    "american_to_decimal",
    "decimal_to_american",
    "implied_probability",
    "calculate_overround",
    "odds_to_implied_probs",
]
