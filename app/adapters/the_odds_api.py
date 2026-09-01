"""
TheOddsAPI v4 Live Polling and Snapshot Odds Ingestion Adapter.
NFL +EV Betting Application (Bet365 Canada vs. Sharp Devig & FantasyPoints).
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

import httpx

from app.adapters.base import BaseOddsAdapter
from app.core.normalizer import PlayerNameNormalizer, TeamNormalizer
from app.schemas.odds import Bookmaker, Event, MarketOffer, MarketOutcome, OddsValue

logger = logging.getLogger(__name__)


class OddsAPIQuotaExceededError(Exception):
    """Raised when TheOddsAPI rate limit or monthly credit quota is exhausted."""
    pass


class TheOddsAPIAdapter(BaseOddsAdapter):
    """
    Ingestion adapter for The-Odds-API v4 JSON API and offline snapshots.

    Supports:
    - NFL core markets: h2h (moneyline), spreads, totals.
    - NFL player props: player_pass_yds, player_pass_tds, player_rush_yds,
      player_rec_yds, player_receptions, player_anytime_td, player_pass_interceptions.
    - Bookmaker filtering and canonicalization (bet365, pinnacle, circa, draftkings, fanduel).
    - API credit tracking via response headers.
    - Seamless mock/offline fallback mode when API key is missing or invalid.
    """

    DEFAULT_BASE_URL: str = "https://api.the-odds-api.com/v4"
    SPORT_KEY_NFL: str = "americanfootball_nfl"

    CORE_MARKETS: list[str] = ["h2h", "spreads", "totals"]
    PLAYER_PROP_MARKETS: list[str] = [
        "player_pass_yds",
        "player_pass_tds",
        "player_rush_yds",
        "player_rec_yds",
        "player_receptions",
        "player_anytime_td",
        "player_pass_interceptions",
    ]

    TARGET_BOOKMAKERS: set[str] = {
        "bet365",
        "bet365_us",
        "pinnacle",
        "circa",
        "circasports",
        "draftkings",
        "fanduel",
        "williamhill_us",
        "betmgm",
    }

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str = DEFAULT_BASE_URL,
        regions: str = "us,eu",
        odds_format: str = "decimal",
        timeout_seconds: float = 10.0,
        mock_fallback: bool = True,
        sample_data_path: Path | str | None = None,
    ) -> None:
        is_live_flag = bool(api_key and api_key.strip().upper() != "MOCK")
        super().__init__(name="TheOddsAPIAdapter", is_live=is_live_flag)
        self.api_key = api_key.strip() if api_key else None
        self.base_url = base_url.rstrip("/")
        self.regions = regions
        self.odds_format = odds_format
        self.timeout_seconds = timeout_seconds
        self.mock_fallback = mock_fallback

        # Path to fallback sample snapshot
        if sample_data_path:
            self.sample_data_path = Path(sample_data_path)
        else:
            self.sample_data_path = Path(__file__).resolve().parent.parent.parent / "sample_data" / "odds_snapshot_sample.json"

        # Rate limit and credit tracking state
        self.remaining_requests: int | None = None
        self.used_requests: int | None = None
        self.last_request_cost: int | None = None

    async def fetch_odds(
        self,
        sport_key: str = SPORT_KEY_NFL,
        markets: list[str] | None = None,
        event_ids: list[str] | None = None,
        bookmakers: list[str] | None = None,
        fetch_player_props: bool = True,
    ) -> list[Event]:
        """
        Fetch live odds from TheOddsAPI v4 with fallback to mock data on missing key/error.

        Args:
            sport_key: Sport identifier, default 'americanfootball_nfl'.
            markets: List of core market keys, defaults to ['h2h', 'spreads', 'totals'].
            event_ids: Optional list of specific event IDs to query.
            bookmakers: Optional list of bookmaker keys to include.
            fetch_player_props: If True, fetches detailed props per event.

        Returns:
            list[Event]: Parsed and normalized Event models.
        """
        if not self.is_live or not self.api_key:
            logger.info("TheOddsAPI live API key not configured. Using offline mock snapshot.")
            return self.load_mock_snapshot()

        target_markets = markets or self.CORE_MARKETS
        url = f"{self.base_url}/sports/{sport_key}/odds"
        params: dict[str, Any] = {
            "apiKey": self.api_key,
            "regions": self.regions,
            "markets": ",".join(target_markets),
            "oddsFormat": self.odds_format,
        }
        if bookmakers:
            params["bookmakers"] = ",".join(bookmakers)

        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                response = await client.get(url, params=params)
                self._extract_rate_limits(response.headers)

                if response.status_code == 401:
                    logger.warning("TheOddsAPI returned 401 Unauthorized (invalid API key).")
                    if self.mock_fallback:
                        return self.load_mock_snapshot()
                    response.raise_for_status()
                elif response.status_code == 429:
                    logger.error("TheOddsAPI credit quota or rate limit exceeded (429).")
                    if self.mock_fallback:
                        return self.load_mock_snapshot()
                    raise OddsAPIQuotaExceededError("TheOddsAPI quota exceeded.")

                response.raise_for_status()
                raw_events = response.json()
                events = self.parse_payload(raw_events)

                # Fetch player props per event if requested
                if fetch_player_props:
                    for event in events:
                        try:
                            prop_offers = await self.fetch_event_props(
                                event_id=event.id,
                                sport_key=sport_key,
                                client=client,
                                bookmakers=bookmakers,
                            )
                            self._merge_event_props(event, prop_offers)
                        except Exception as prop_err:
                            logger.warning(f"Failed to fetch props for event {event.id}: {prop_err}")

                return self._validate_events(events)

        except Exception as e:
            logger.error(f"Error communicating with TheOddsAPI: {e}")
            if self.mock_fallback:
                logger.info("Falling back to local mock snapshot due to network/API error.")
                return self.load_mock_snapshot()
            raise

    async def fetch_event_props(
        self,
        event_id: str,
        sport_key: str = SPORT_KEY_NFL,
        client: httpx.AsyncClient | None = None,
        markets: list[str] | None = None,
        bookmakers: list[str] | None = None,
    ) -> list[MarketOffer]:
        """Fetch player props for a specific event."""
        if not self.is_live or not self.api_key:
            return []

        prop_markets = markets or self.PLAYER_PROP_MARKETS
        url = f"{self.base_url}/sports/{sport_key}/events/{event_id}/odds"
        params: dict[str, Any] = {
            "apiKey": self.api_key,
            "regions": self.regions,
            "markets": ",".join(prop_markets),
            "oddsFormat": self.odds_format,
        }
        if bookmakers:
            params["bookmakers"] = ",".join(bookmakers)

        close_client = False
        if client is None:
            client = httpx.AsyncClient(timeout=self.timeout_seconds)
            close_client = True

        try:
            response = await client.get(url, params=params)
            self._extract_rate_limits(response.headers)
            if response.status_code == 200:
                data = response.json()
                event = self.parse_event_payload(data)
                offers: list[MarketOffer] = []
                for book in event.bookmakers:
                    offers.extend(book.markets)
                return offers
            return []
        finally:
            if close_client:
                await client.aclose()

    def parse_payload(self, data: Any) -> list[Event]:
        """Parse raw TheOddsAPI v4 response list or dict into Event models."""
        if isinstance(data, str):
            data = json.loads(data)

        if isinstance(data, dict):
            # Single event response
            return [self.parse_event_payload(data)]
        elif isinstance(data, list):
            # Multi-event list response
            events: list[Event] = []
            for item in data:
                if isinstance(item, dict):
                    ev = self.parse_event_payload(item)
                    if ev.id:
                        events.append(ev)
            return events
        return []

    def parse_event_payload(self, raw_event: dict[str, Any]) -> Event:
        """Parse a single raw event JSON object."""
        event_id = str(raw_event.get("id", ""))
        sport_key = raw_event.get("sport_key", self.SPORT_KEY_NFL)
        sport_title = raw_event.get("sport_title", "NFL")

        # Parse timestamps
        commence_time_raw = raw_event.get("commence_time")
        if isinstance(commence_time_raw, str):
            commence_time = datetime.fromisoformat(commence_time_raw.replace("Z", "+00:00"))
        elif isinstance(commence_time_raw, datetime):
            commence_time = commence_time_raw
        else:
            commence_time = datetime.now(timezone.utc)

        raw_home = raw_event.get("home_team", "")
        raw_away = raw_event.get("away_team", "")
        home_canonical = TeamNormalizer.canonical_team(raw_home)
        away_canonical = TeamNormalizer.canonical_team(raw_away)

        bookmakers: list[Bookmaker] = []
        for raw_bm in raw_event.get("bookmakers", []):
            bm = self.parse_bookmaker_payload(raw_bm, home_team=home_canonical, away_team=away_canonical)
            if bm.markets:
                bookmakers.append(bm)

        return Event(
            id=event_id,
            sport_key=sport_key,
            sport_title=sport_title,
            commence_time=commence_time,
            home_team=raw_home,
            away_team=raw_away,
            home_team_canonical=home_canonical,
            away_team_canonical=away_canonical,
            bookmakers=bookmakers,
        )

    def parse_bookmaker_payload(
        self,
        raw_bm: dict[str, Any],
        home_team: str = "",
        away_team: str = "",
    ) -> Bookmaker:
        """Parse raw bookmaker object and its market offerings."""
        bm_key = str(raw_bm.get("key", "")).lower().strip()
        # Canonicalize bookmaker key (e.g. bet365_us -> bet365, circasports -> circa)
        if bm_key.startswith("bet365"):
            bm_key = "bet365"
        elif bm_key in ("circasports", "circa"):
            bm_key = "circa"

        bm_title = raw_bm.get("title", bm_key.title())
        last_update_raw = raw_bm.get("last_update")
        last_update = None
        if isinstance(last_update_raw, str):
            try:
                last_update = datetime.fromisoformat(last_update_raw.replace("Z", "+00:00"))
            except ValueError:
                pass

        markets: list[MarketOffer] = []
        for raw_mkt in raw_bm.get("markets", []):
            offer = self.parse_market_payload(raw_mkt, bookmaker=bm_key, home_team=home_team, away_team=away_team)
            if offer.outcomes:
                markets.append(offer)

        return Bookmaker(
            key=bm_key,
            title=bm_title,
            last_update=last_update,
            markets=markets,
        )

    def parse_market_payload(
        self,
        raw_mkt: dict[str, Any],
        bookmaker: str = "unknown",
        home_team: str = "",
        away_team: str = "",
    ) -> MarketOffer:
        """Parse a market object (player prop or core line)."""
        market_key = str(raw_mkt.get("key", "")).lower().strip()
        last_update_raw = raw_mkt.get("last_update")
        last_update = None
        if isinstance(last_update_raw, str):
            try:
                last_update = datetime.fromisoformat(last_update_raw.replace("Z", "+00:00"))
            except ValueError:
                pass

        outcomes: list[MarketOutcome] = []
        player_name = None
        player_canonical = None
        market_point = None

        for raw_out in raw_mkt.get("outcomes", []):
            outcome = self.parse_outcome_payload(
                raw_out,
                market_key=market_key,
                home_team=home_team,
                away_team=away_team,
            )
            if outcome is not None:
                outcomes.append(outcome)
                if outcome.player_name and not player_name:
                    player_name = outcome.player_name
                    player_canonical = outcome.player_canonical
                if outcome.point is not None and market_point is None:
                    market_point = outcome.point

        label = self._format_market_label(market_key)
        if player_name:
            label = f"{player_name} - {label}"

        return MarketOffer(
            market_key=market_key,
            label=label,
            player_name=player_name,
            player_canonical=player_canonical,
            point=market_point,
            bookmaker=bookmaker,
            last_update=last_update,
            outcomes=outcomes,
        )

    def parse_outcome_payload(
        self,
        raw_out: dict[str, Any],
        market_key: str = "",
        home_team: str = "",
        away_team: str = "",
    ) -> MarketOutcome | None:
        """Parse an outcome object into MarketOutcome."""
        raw_name = str(raw_out.get("name", "")).strip()
        raw_desc = raw_out.get("description")
        price_val = raw_out.get("price")
        point_val = raw_out.get("point")

        if price_val is None:
            return None

        # Build OddsValue
        try:
            if isinstance(price_val, int) or (isinstance(price_val, float) and abs(price_val) >= 100):
                odds = OddsValue.from_american(int(price_val))
            else:
                odds = OddsValue.from_decimal(float(price_val))
        except Exception:
            return None

        point = float(point_val) if point_val is not None else None

        player_name = None
        player_canonical = None
        outcome_type = "over"

        if raw_desc:
            # Player prop outcome
            player_name = str(raw_desc).strip()
            player_canonical = PlayerNameNormalizer.clean_name(player_name)
            name_lower = raw_name.lower()
            if "over" in name_lower:
                outcome_type = "over"
            elif "under" in name_lower:
                outcome_type = "under"
            elif "yes" in name_lower:
                outcome_type = "yes"
            elif "no" in name_lower:
                outcome_type = "no"
            else:
                outcome_type = name_lower
        else:
            # Core market outcome
            name_lower = raw_name.lower()
            if market_key == "totals":
                outcome_type = "over" if "over" in name_lower else "under"
            elif market_key in ("h2h", "spreads"):
                norm_team = TeamNormalizer.canonical_team(raw_name)
                if norm_team == home_team:
                    outcome_type = "home"
                elif norm_team == away_team:
                    outcome_type = "away"
                else:
                    outcome_type = name_lower
            else:
                outcome_type = name_lower

        return MarketOutcome(
            name=raw_name,
            description=str(raw_desc) if raw_desc else None,
            odds=odds,
            point=point,
            outcome_type=outcome_type,
            player_name=player_name,
            player_canonical=player_canonical,
        )

    def load_mock_snapshot(self) -> list[Event]:
        """Load and parse sample odds snapshot from local JSON file."""
        if not self.sample_data_path.exists():
            logger.warning(f"Sample odds snapshot not found at {self.sample_data_path}")
            return []
        try:
            with open(self.sample_data_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return self.parse_payload(data)
        except Exception as e:
            logger.error(f"Failed to load sample snapshot: {e}")
            return []

    def _extract_rate_limits(self, headers: Any) -> None:
        """Extract TheOddsAPI credit usage and remaining quota from response headers."""
        try:
            if "x-requests-remaining" in headers:
                self.remaining_requests = int(headers["x-requests-remaining"])
            if "x-requests-used" in headers:
                self.used_requests = int(headers["x-requests-used"])
            if "x-requests-last" in headers:
                self.last_request_cost = int(headers["x-requests-last"])
        except Exception as e:
            logger.debug(f"Could not parse rate limit headers: {e}")

    def _merge_event_props(self, event: Event, prop_offers: list[MarketOffer]) -> None:
        """Merge fetched prop offers into existing event bookmaker records."""
        book_map = {b.key.lower(): b for b in event.bookmakers}
        for offer in prop_offers:
            bm_key = offer.bookmaker.lower()
            if bm_key in book_map:
                book_map[bm_key].markets.append(offer)
            else:
                new_bm = Bookmaker(
                    key=bm_key,
                    title=bm_key.title(),
                    markets=[offer],
                )
                event.bookmakers.append(new_bm)
                book_map[bm_key] = new_bm

    @staticmethod
    def _format_market_label(key: str) -> str:
        """Return human-readable market label."""
        labels = {
            "h2h": "Moneyline",
            "spreads": "Point Spread",
            "totals": "Game Total",
            "player_pass_yds": "Passing Yards",
            "player_pass_tds": "Passing Touchdowns",
            "player_rush_yds": "Rushing Yards",
            "player_rec_yds": "Receiving Yards",
            "player_receptions": "Player Receptions",
            "player_anytime_td": "Anytime Touchdown",
            "player_pass_interceptions": "Pass Interceptions",
        }
        return labels.get(key, key.replace("_", " ").title())
