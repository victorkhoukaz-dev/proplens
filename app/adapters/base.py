"""
Base adapter interfaces for odds and player projections ingestion.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Sequence

from app.schemas.odds import Event
from app.schemas.projections import PlayerProjection


class BaseOddsAdapter(ABC):
    """Abstract base class for all odds ingestion adapters."""

    def __init__(self, name: str = "BaseOddsAdapter", is_live: bool = False):
        self.name = name
        self.is_live = is_live

    @abstractmethod
    async def fetch_odds(self, **kwargs: Any) -> list[Event]:
        """Fetch odds asynchronously from the provider or data source.

        Returns:
            list[Event]: List of normalized, validated Event domain models.
        """
        raise NotImplementedError("Subclasses must implement fetch_odds")

    @abstractmethod
    def parse_payload(self, data: Any) -> list[Event]:
        """Parse raw payload (JSON dict/list, CSV string, bytes) into Events.

        Args:
            data: Raw data structure to parse.

        Returns:
            list[Event]: List of normalized, validated Event domain models.
        """
        raise NotImplementedError("Subclasses must implement parse_payload")

    def _validate_events(self, events: Sequence[Event]) -> list[Event]:
        """Defensive post-validation of parsed events."""
        valid_events: list[Event] = []
        for ev in events:
            if isinstance(ev, Event) and ev.id and ev.bookmakers:
                valid_events.append(ev)
        return valid_events


class BaseProjectionAdapter(ABC):
    """Abstract base class for player projection ingestion adapters."""

    def __init__(self, name: str = "BaseProjectionAdapter"):
        self.name = name

    @abstractmethod
    def parse_projections(self, data: Any, **kwargs: Any) -> list[PlayerProjection]:
        """Parse raw projection data (CSV text, DataFrame, Excel bytes) into PlayerProjections.

        Args:
            data: Raw input data (file content, string, or structured object).

        Returns:
            list[PlayerProjection]: List of validated PlayerProjection models.
        """
        raise NotImplementedError("Subclasses must implement parse_projections")
