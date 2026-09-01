"""
Pydantic v2 schemas for statistical player projections and category mappings.
"""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class StatCategory(str, Enum):
    """
    Standardized NFL player prop and statistical categories with mapping utilities.
    """
    # Passing
    PASSING_YARDS = "passing_yards"
    PASSING_TDS = "passing_tds"
    PASSING_INTERCEPTIONS = "passing_interceptions"
    PASSING_ATTEMPTS = "passing_attempts"
    PASSING_COMPLETIONS = "passing_completions"

    # Rushing
    RUSHING_YARDS = "rushing_yards"
    RUSHING_ATTEMPTS = "rushing_attempts"
    RUSHING_TDS = "rushing_tds"

    # Receiving
    RECEIVING_YARDS = "receiving_yards"
    RECEPTIONS = "receptions"
    RECEIVING_TARGETS = "receiving_targets"
    RECEIVING_TDS = "receiving_tds"

    # Scoring & Defense
    ANYTIME_TD = "anytime_td"
    FIELD_GOALS = "field_goals"
    SACKS = "sacks"
    TACKLES_ASSISTS = "tackles_assists"

    @classmethod
    def from_market_key(cls, key: str) -> StatCategory | None:
        """
        Map TheOddsAPI / sportsbook market key to StatCategory.
        """
        if not key or not isinstance(key, str):
            return None
        mapping = {
            "player_pass_yds": cls.PASSING_YARDS,
            "player_pass_tds": cls.PASSING_TDS,
            "player_pass_interceptions": cls.PASSING_INTERCEPTIONS,
            "player_pass_attempts": cls.PASSING_ATTEMPTS,
            "player_pass_completions": cls.PASSING_COMPLETIONS,
            "player_rush_yds": cls.RUSHING_YARDS,
            "player_rush_attempts": cls.RUSHING_ATTEMPTS,
            "player_rush_tds": cls.RUSHING_TDS,
            "player_rec_yds": cls.RECEIVING_YARDS,
            "player_receptions": cls.RECEPTIONS,
            "player_rec_targets": cls.RECEIVING_TARGETS,
            "player_anytime_td": cls.ANYTIME_TD,
            "player_field_goals": cls.FIELD_GOALS,
            "player_sacks": cls.SACKS,
            "player_tackles_assists": cls.TACKLES_ASSISTS,
        }
        return mapping.get(key.strip().lower())

    @classmethod
    def from_fantasypoints_header(cls, header: str) -> StatCategory | None:
        """
        Map FantasyPoints CSV/Excel column header to StatCategory.
        """
        if not header or not isinstance(header, str):
            return None
        normalized = header.strip().lower().replace("_", " ").replace("-", " ")
        mapping = {
            "pass yds": cls.PASSING_YARDS,
            "pass yards": cls.PASSING_YARDS,
            "passing yds": cls.PASSING_YARDS,
            "passing yards": cls.PASSING_YARDS,
            "pass td": cls.PASSING_TDS,
            "pass tds": cls.PASSING_TDS,
            "passing td": cls.PASSING_TDS,
            "passing tds": cls.PASSING_TDS,
            "pass int": cls.PASSING_INTERCEPTIONS,
            "pass ints": cls.PASSING_INTERCEPTIONS,
            "interceptions": cls.PASSING_INTERCEPTIONS,
            "int": cls.PASSING_INTERCEPTIONS,
            "pass att": cls.PASSING_ATTEMPTS,
            "pass attempts": cls.PASSING_ATTEMPTS,
            "pass comp": cls.PASSING_COMPLETIONS,
            "pass completions": cls.PASSING_COMPLETIONS,
            "rush yds": cls.RUSHING_YARDS,
            "rush yards": cls.RUSHING_YARDS,
            "rushing yds": cls.RUSHING_YARDS,
            "rushing yards": cls.RUSHING_YARDS,
            "rush att": cls.RUSHING_ATTEMPTS,
            "rush attempts": cls.RUSHING_ATTEMPTS,
            "rush td": cls.RUSHING_TDS,
            "rush tds": cls.RUSHING_TDS,
            "rec yds": cls.RECEIVING_YARDS,
            "rec yards": cls.RECEIVING_YARDS,
            "receiving yds": cls.RECEIVING_YARDS,
            "receiving yards": cls.RECEIVING_YARDS,
            "rec": cls.RECEPTIONS,
            "receptions": cls.RECEPTIONS,
            "rec targets": cls.RECEIVING_TARGETS,
            "targets": cls.RECEIVING_TARGETS,
            "td": cls.ANYTIME_TD,
            "anytime td": cls.ANYTIME_TD,
            "anytime touchdown": cls.ANYTIME_TD,
            "fg": cls.FIELD_GOALS,
            "field goals": cls.FIELD_GOALS,
            "sacks": cls.SACKS,
            "tackles": cls.TACKLES_ASSISTS,
        }
        return mapping.get(normalized)

    def to_market_key(self) -> str:
        """
        Map StatCategory to TheOddsAPI market key format.
        """
        reverse_map = {
            self.PASSING_YARDS: "player_pass_yds",
            self.PASSING_TDS: "player_pass_tds",
            self.PASSING_INTERCEPTIONS: "player_pass_interceptions",
            self.PASSING_ATTEMPTS: "player_pass_attempts",
            self.PASSING_COMPLETIONS: "player_pass_completions",
            self.RUSHING_YARDS: "player_rush_yds",
            self.RUSHING_ATTEMPTS: "player_rush_attempts",
            self.RUSHING_TDS: "player_rush_tds",
            self.RECEIVING_YARDS: "player_rec_yds",
            self.RECEPTIONS: "player_receptions",
            self.RECEIVING_TARGETS: "player_rec_targets",
            self.ANYTIME_TD: "player_anytime_td",
            self.FIELD_GOALS: "player_field_goals",
            self.SACKS: "player_sacks",
            self.TACKLES_ASSISTS: "player_tackles_assists",
        }
        return reverse_map[self]

    @property
    def is_continuous(self) -> bool:
        """
        True for continuous yardage distributions (Log-Normal/Normal),
        False for discrete counts (Poisson/NegBin).
        """
        return self in (
            StatCategory.PASSING_YARDS,
            StatCategory.RUSHING_YARDS,
            StatCategory.RECEIVING_YARDS,
        )


class Position(str, Enum):
    """Standard NFL Player Positions."""
    QB = "QB"
    RB = "RB"
    WR = "WR"
    TE = "TE"
    K = "K"
    DEF = "DEF"
    DST = "DST"
    FLEX = "FLEX"


class PlayerProjection(BaseModel):
    """
    Represents an expected statistical projection for an NFL player.
    """
    model_config = ConfigDict(populate_by_name=True, from_attributes=True)

    player_name: str = Field(..., description="Raw player name (e.g. 'Patrick Mahomes II')")
    canonical_name: str | None = Field(default=None, description="Normalized canonical name (e.g. 'Patrick Mahomes')")
    team: str = Field(..., description="Canonical team abbreviation (e.g. 'KC', 'BUF')")
    position: str = Field(..., description="Player position (e.g. 'QB', 'WR', 'RB', 'TE')")
    opponent: str | None = Field(default=None, description="Opponent team abbreviation")
    stat_category: StatCategory = Field(..., description="Standardized statistical category")
    projection_mean: float = Field(..., description="Projected mean expected value (E[Y])")
    projection_median: float | None = Field(default=None, description="Projected median value if provided")
    projection_floor: float | None = Field(default=None, description="Projected floor value")
    projection_ceiling: float | None = Field(default=None, description="Projected ceiling value")
    projection_std: float | None = Field(default=None, description="Custom projection standard deviation override")
    source: str = Field(default="fantasypoints", description="Source provider")
    season: int = Field(default=2026, description="NFL season year")
    week: int | None = Field(default=None, description="NFL week number")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Additional provider metadata")
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Timestamp of projection record"
    )
