"""
app.db.cache: Thread-safe in-memory caching store with multi-index query filtering.
"""
from __future__ import annotations

import logging
import threading
from datetime import datetime, timezone
from typing import Any, Callable

from app.schemas.ev import MatchedEVOpportunity
from app.schemas.odds import MarketOffer
from app.schemas.projections import PlayerProjection

logger = logging.getLogger(__name__)


class AppSettings:
    def __init__(
        self,
        bankroll: float = 1000.0,
        kelly_fraction: float = 0.25,
        w_market: float = 0.60,
        w_model: float = 0.40,
        min_ev_threshold: float = 0.0,
        min_stake: float = 5.0,
        odds_api_key: str = "",
        api_provider: str = "oddspapi",
        auto_refresh_seconds: int = 60,
    ):
        self.bankroll = bankroll
        self.kelly_fraction = kelly_fraction
        self.w_market = w_market
        self.w_model = w_model
        self.min_ev_threshold = min_ev_threshold
        self.min_stake = min_stake
        self.odds_api_key = odds_api_key
        self.api_provider = api_provider  # "oddspapi" or "the_odds_api"
        self.auto_refresh_seconds = auto_refresh_seconds

    def to_dict(self) -> dict[str, Any]:
        return {
            "bankroll": self.bankroll,
            "kelly_fraction": self.kelly_fraction,
            "w_market": self.w_market,
            "w_model": self.w_model,
            "min_ev_threshold": self.min_ev_threshold,
            "min_stake": self.min_stake,
            "api_provider": self.api_provider,
            "has_odds_api_key": bool(self.odds_api_key.strip()),
            "odds_api_key_masked": (
                f"{self.odds_api_key[:4]}...{self.odds_api_key[-4:]}"
                if len(self.odds_api_key) > 8
                else ("****" if self.odds_api_key else "")
            ),
            "auto_refresh_seconds": self.auto_refresh_seconds,
        }

    def to_storage_dict(self) -> dict[str, Any]:
        """Return the complete local settings record, including the API key."""
        return {
            "bankroll": self.bankroll,
            "kelly_fraction": self.kelly_fraction,
            "w_market": self.w_market,
            "w_model": self.w_model,
            "min_ev_threshold": self.min_ev_threshold,
            "min_stake": self.min_stake,
            "odds_api_key": self.odds_api_key,
            "api_provider": self.api_provider,
            "auto_refresh_seconds": self.auto_refresh_seconds,
        }


class StateCache:
    """
    High-performance thread-safe in-memory cache supporting sub-5ms lookups.
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._opportunities: dict[str, MatchedEVOpportunity] = {}
        self._projections: dict[str, PlayerProjection] = {}
        self._events: list[Any] = []
        self._odds_offers: list[MarketOffer] = []
        self._settings: AppSettings = AppSettings()
        self._last_updated: datetime = datetime.now(timezone.utc)
        self._listeners: list[Callable[[], None]] = []

    def set_settings(self, **kwargs: Any) -> AppSettings:
        with self._lock:
            for k, v in kwargs.items():
                if hasattr(self._settings, k) and v is not None:
                    setattr(self._settings, k, v)
            return self._settings

    def get_settings(self) -> AppSettings:
        with self._lock:
            return self._settings

    def store_projections(self, projections: list[PlayerProjection]) -> None:
        with self._lock:
            for p in projections:
                name_key = p.canonical_name or p.player_name
                key = f"{name_key}_{p.stat_category.value}".lower()
                self._projections[key] = p
            self._last_updated = datetime.now(timezone.utc)

    def replace_projections(self, projections: list[PlayerProjection]) -> None:
        """Replace the current projection set with one coherent imported source."""
        with self._lock:
            self._projections = {}
            for p in projections:
                name_key = p.canonical_name or p.player_name
                key = f"{name_key}_{p.stat_category.value}".lower()
                self._projections[key] = p
            self._last_updated = datetime.now(timezone.utc)

    def get_projections(self) -> list[PlayerProjection]:
        with self._lock:
            return list(self._projections.values())

    def store_events(self, events: list[Event]) -> None:
        with self._lock:
            self._events = list(events)
            self._last_updated = datetime.now(timezone.utc)

    def get_events(self) -> list[Event]:
        with self._lock:
            return list(self._events)

    def store_odds_offers(self, offers: list[MarketOffer]) -> None:
        with self._lock:
            self._odds_offers = list(offers)
            self._last_updated = datetime.now(timezone.utc)

    def get_odds_offers(self) -> list[MarketOffer]:
        with self._lock:
            return list(self._odds_offers)

    def store_opportunities(self, opportunities: list[MatchedEVOpportunity]) -> None:
        with self._lock:
            self._opportunities = {opp.id: opp for opp in opportunities}
            self._last_updated = datetime.now(timezone.utc)

    def get_opportunity(self, opp_id: str) -> MatchedEVOpportunity | None:
        with self._lock:
            return self._opportunities.get(opp_id)

    def get_opportunities(
        self,
        min_ev: float | None = None,
        market_category: str | None = None,
        search_query: str | None = None,
        bookmaker: str | None = None,
        sort_by: str = "blended_ev",
        sort_desc: bool = True,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list[MatchedEVOpportunity], int]:
        """
        Fast in-memory filtered multi-index query.
        """
        with self._lock:
            items = list(self._opportunities.values())

            # 1. Filter by minimum EV
            threshold = min_ev if min_ev is not None else self._settings.min_ev_threshold
            items = [opp for opp in items if opp.blended_ev >= threshold]

            # 2. Filter by market category
            if market_category and market_category.lower() != "all":
                items = [
                    opp for opp in items
                    if str(opp.market_key).lower() == market_category.lower()
                    or str(opp.market_label).lower() == market_category.lower()
                ]

            # 3. Filter by search query (player, team, matchup)
            if search_query and search_query.strip():
                q = search_query.strip().lower()
                items = [
                    opp for opp in items
                    if (opp.player_name and q in opp.player_name.lower())
                    or (opp.team and q in opp.team.lower())
                    or (q in opp.game.lower())
                    or (q in opp.market_key.lower())
                    or (q in opp.market_label.lower())
                ]

            # 4. Filter by bookmaker
            if bookmaker and bookmaker.lower() != "all":
                items = [
                    opp for opp in items
                    if opp.target_book.lower() == bookmaker.lower()
                ]

            # 5. Sorting
            def sort_key(opp: MatchedEVOpportunity) -> Any:
                if sort_by == "blended_ev":
                    return opp.blended_ev
                elif sort_by == "market_ev":
                    return opp.market_implied_ev if opp.market_implied_ev is not None else -9999.0
                elif sort_by == "model_ev":
                    return opp.model_implied_ev if opp.model_implied_ev is not None else -9999.0
                elif sort_by == "stake":
                    return opp.recommended_stake
                elif sort_by == "odds":
                    return opp.target_decimal
                elif sort_by == "edge":
                    return opp.edge_pct
                elif sort_by == "player":
                    return opp.player_name or opp.game
                return opp.blended_ev

            items.sort(key=sort_key, reverse=sort_desc)
            total_count = len(items)

            # 6. Pagination
            paginated = items[offset : offset + limit] if limit > 0 else items
            return paginated, total_count

    def clear(self) -> None:
        with self._lock:
            self._opportunities.clear()
            self._projections.clear()
            self._events.clear()
            self._odds_offers.clear()
            self._last_updated = datetime.now(timezone.utc)


# Global singleton instance
cache = StateCache()
