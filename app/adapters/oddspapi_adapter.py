"""OddsPapi v4 live NFL odds ingestion adapter."""
from __future__ import annotations

import asyncio
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, ClassVar

import httpx

from app.adapters.base import BaseOddsAdapter
from app.core.normalizer import PlayerNameNormalizer, TeamNormalizer
from app.db.raw_odds_snapshot_store import RawOddsSnapshotStore
from app.schemas.odds import Bookmaker, Event, MarketOffer, MarketOutcome, OddsValue, OutcomeType

logger = logging.getLogger(__name__)


class OddsPapiAdapter(BaseOddsAdapter):
    """Translate OddsPapi v4 NFL odds into the application's domain models."""

    DEFAULT_BASE_URL = "https://api.oddspapi.io/v4"
    NFL_SPORT_ID = 14
    NFL_TOURNAMENT_ID = 31
    DEFAULT_BOOKMAKERS = ("bet365", "pinnacle")
    _market_catalog_cache: ClassVar[dict[str, dict[str, Any]] | None] = None

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str = DEFAULT_BASE_URL,
        odds_format: str = "decimal",
        timeout_seconds: float = 12.0,
        mock_fallback: bool = True,
        request_spacing_seconds: float = 1.05,
        raw_snapshot_store: RawOddsSnapshotStore | None = None,
    ) -> None:
        is_live = bool(api_key and api_key.strip().upper() != "MOCK")
        super().__init__(name="OddsPapiAdapter", is_live=is_live)
        self.api_key = api_key.strip() if api_key else None
        self.base_url = base_url.rstrip("/")
        self.odds_format = odds_format
        self.timeout_seconds = timeout_seconds
        self.mock_fallback = mock_fallback
        self.request_spacing_seconds = request_spacing_seconds
        self.raw_snapshot_store = raw_snapshot_store
        self.last_raw_snapshot_path: str | None = None
        self.remaining_requests: int | None = None
        self.used_requests: int | None = None

    async def fetch_odds(
        self,
        bookmakers: list[str] | None = None,
        tournament_ids: list[int] | None = None,
    ) -> list[Event]:
        """Fetch NFL odds for Bet365 and Pinnacle in two provider requests."""
        if not self.is_live or not self.api_key:
            logger.info("OddsPapi key not configured. Using the offline snapshot.")
            return self.load_mock_snapshot()

        target_books = bookmakers or list(self.DEFAULT_BOOKMAKERS)
        target_tournaments = tournament_ids or [self.NFL_TOURNAMENT_ID]

        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                market_catalog = type(self)._market_catalog_cache
                raw_market_catalog_response: Any | None = None
                if market_catalog is None:
                    market_response = await client.get(
                        f"{self.base_url}/markets",
                        params={
                            "apiKey": self.api_key,
                            "sportId": self.NFL_SPORT_ID,
                            "language": "en",
                        },
                    )
                    self._raise_for_api_error(market_response, "market catalogue")
                    raw_market_catalog_response = market_response.json()
                    market_catalog = self.build_market_catalog(raw_market_catalog_response)
                    type(self)._market_catalog_cache = market_catalog

                events_by_id: dict[str, Event] = {}
                raw_bookmaker_responses: dict[str, Any] = {}
                for index, bookmaker in enumerate(target_books):
                    if index and self.request_spacing_seconds > 0:
                        await asyncio.sleep(self.request_spacing_seconds)
                    odds_response = await client.get(
                        f"{self.base_url}/odds-by-tournaments",
                        params={
                            "apiKey": self.api_key,
                            "tournamentIds": ",".join(str(value) for value in target_tournaments),
                            "bookmaker": bookmaker,
                            "language": "en",
                            "verbosity": 3,
                            "oddsFormat": self.odds_format,
                        },
                    )
                    self._extract_rate_limits(odds_response.headers)
                    self._raise_for_api_error(odds_response, f"{bookmaker} NFL odds")

                    payload = odds_response.json()
                    raw_bookmaker_responses[bookmaker.lower()] = payload
                    fixtures = payload if isinstance(payload, list) else [payload]
                    parsed_events = self.parse_fixtures(
                        fixtures,
                        market_catalog,
                        allowed_bookmakers={bookmaker.lower()},
                    )
                    self._merge_events(events_by_id, parsed_events)

                if self.raw_snapshot_store is not None:
                    try:
                        snapshot_path = self.raw_snapshot_store.save(
                            bookmaker_responses=raw_bookmaker_responses,
                            market_catalog_response=raw_market_catalog_response,
                            parsed_market_catalog=market_catalog,
                            request_metadata={
                                "base_url": self.base_url,
                                "sport_id": self.NFL_SPORT_ID,
                                "tournament_ids": target_tournaments,
                                "bookmakers": target_books,
                                "odds_format": self.odds_format,
                                "market_catalog_source": (
                                    "live_response" if raw_market_catalog_response is not None else "memory_cache"
                                ),
                            },
                        )
                        self.last_raw_snapshot_path = str(snapshot_path)
                        logger.info("Saved redacted OddsPapi diagnostic snapshot: %s", snapshot_path.name)
                    except OSError as snapshot_error:
                        logger.warning("Could not save OddsPapi diagnostic snapshot: %s", snapshot_error)

                events = list(events_by_id.values())
                if events:
                    return events

                if self.mock_fallback:
                    logger.warning("OddsPapi returned no NFL events; using the offline snapshot.")
                    return self.load_mock_snapshot()
                return []
        except Exception as exc:
            safe_exception: Exception = exc
            if isinstance(exc, httpx.RequestError):
                safe_exception = RuntimeError(
                    "Could not connect to OddsPapi. Check your internet connection and try again."
                )
            logger.error("OddsPapi live fetch failed: %s", safe_exception)
            if self.mock_fallback:
                logger.info("Using the offline snapshot after the OddsPapi error.")
                return self.load_mock_snapshot()
            if safe_exception is exc:
                raise
            raise safe_exception from exc

    @staticmethod
    def _merge_events(events_by_id: dict[str, Event], incoming_events: list[Event]) -> None:
        """Combine single-book responses for the same NFL fixture."""
        for incoming in incoming_events:
            existing = events_by_id.get(incoming.id)
            if existing is None:
                events_by_id[incoming.id] = incoming
                continue
            existing_keys = {book.key for book in existing.bookmakers}
            existing.bookmakers.extend(
                book for book in incoming.bookmakers if book.key not in existing_keys
            )

    def parse_payload(self, data: Any) -> list[Event]:
        """Parse an offline OddsPapi payload, optionally bundled with markets."""
        market_catalog: dict[str, dict[str, Any]] = {}
        fixtures: Any = data
        if isinstance(data, dict) and "fixtures" in data:
            fixtures = data.get("fixtures") or []
            market_catalog = self.build_market_catalog(data.get("markets") or [])
        elif isinstance(data, dict):
            fixtures = [data]
        if not isinstance(fixtures, list):
            return []
        return self._validate_events(self.parse_fixtures(fixtures, market_catalog))

    @staticmethod
    def _raise_for_api_error(response: httpx.Response, operation: str) -> None:
        if response.status_code == 401:
            raise ValueError("OddsPapi rejected the API key (401 Unauthorized).")
        if response.status_code == 429:
            retry_ms = None
            try:
                body = response.json()
                if isinstance(body, dict):
                    retry_ms = (body.get("error") or {}).get("retryMs")
            except Exception:
                pass
            retry_note = f" Retry after about {retry_ms} ms." if retry_ms else ""
            raise RuntimeError(f"OddsPapi rate limit reached while fetching {operation}.{retry_note}")
        try:
            body = response.json()
        except Exception:
            body = None
        if response.status_code >= 400:
            detail = "Request rejected by the provider."
            if isinstance(body, dict):
                raw_detail = body.get("message") or body.get("details") or body.get("error")
                if raw_detail:
                    detail = str(raw_detail)
            raise RuntimeError(f"OddsPapi {operation} request failed ({response.status_code}): {detail}")
        if isinstance(body, dict) and body.get("error"):
            raise RuntimeError(f"OddsPapi could not fetch {operation}: {body['error']}")

    @classmethod
    def build_market_catalog(cls, raw_markets: Any) -> dict[str, dict[str, Any]]:
        """Index provider market metadata and map it to the app's market keys."""
        if not isinstance(raw_markets, list):
            return {}

        catalog: dict[str, dict[str, Any]] = {}
        for raw_market in raw_markets:
            if not isinstance(raw_market, dict) or raw_market.get("marketId") is None:
                continue
            market_id = str(raw_market["marketId"])
            outcome_names = {
                str(item.get("outcomeId")): str(item.get("outcomeName", ""))
                for item in raw_market.get("outcomes", [])
                if isinstance(item, dict) and item.get("outcomeId") is not None
            }
            catalog[market_id] = {
                "market_name": str(raw_market.get("marketName") or raw_market.get("marketNameShort") or market_id),
                "market_type": str(raw_market.get("marketType") or "").lower(),
                "player_prop": bool(raw_market.get("playerProp")),
                "handicap": raw_market.get("handicap"),
                "outcomes": outcome_names,
                "canonical_key": cls._canonical_market_key(raw_market),
            }
        return catalog

    @staticmethod
    def _canonical_market_key(raw_market: dict[str, Any]) -> str | None:
        name = " ".join(
            str(raw_market.get(field) or "").lower().replace("_", "-")
            for field in ("marketName", "marketNameShort", "marketType")
        )
        player_prop = bool(raw_market.get("playerProp"))

        if player_prop:
            if "passing yard" in name or "pass-yard" in name:
                return "player_pass_yds"
            if "passing touchdown" in name or "passing td" in name or "pass-td" in name:
                return "player_pass_tds"
            if "pass" in name and "interception" in name:
                return "player_pass_interceptions"
            if "rushing yard" in name or "rush-yard" in name:
                return "player_rush_yds"
            if "receiving yard" in name or "receiv-yard" in name:
                return "player_rec_yds"
            if "reception" in name:
                return "player_receptions"
            if any(token in name for token in ("anytime touchdown", "to score td", "to score a touchdown")):
                return "player_anytime_td"
            return None

        market_type = str(raw_market.get("marketType") or "").lower()
        if market_type in {"moneyline", "winner"} or "winner (incl" in name:
            return "h2h"
        if "handicap" in market_type or "spread" in market_type or "handicap" in name:
            return "spreads"
        if market_type == "totals" or "over under" in name or "total points" in name:
            return "totals"
        return None

    def parse_fixtures(
        self,
        fixtures: list[dict[str, Any]],
        market_catalog: dict[str, dict[str, Any]],
        allowed_bookmakers: set[str] | None = None,
    ) -> list[Event]:
        events: list[Event] = []
        for fixture in fixtures:
            if not isinstance(fixture, dict):
                continue
            fixture_id = str(fixture.get("fixtureId") or fixture.get("id") or "")
            if not fixture_id:
                continue

            home_team = str(fixture.get("participant1Name") or fixture.get("homeTeam") or "Home Team")
            away_team = str(fixture.get("participant2Name") or fixture.get("awayTeam") or "Away Team")
            commence_time = self._parse_timestamp(fixture.get("startTime") or fixture.get("commenceTime"))
            last_update = self._parse_timestamp(fixture.get("updatedAt"), default_now=False)
            bookmakers: list[Bookmaker] = []

            raw_books = fixture.get("bookmakerOdds") or {}
            if not isinstance(raw_books, dict):
                continue
            for bookmaker_key, raw_book in raw_books.items():
                normalized_bookmaker = str(bookmaker_key).lower()
                if allowed_bookmakers is not None and normalized_bookmaker not in allowed_bookmakers:
                    continue
                if not isinstance(raw_book, dict):
                    continue
                if raw_book.get("bookmakerIsActive") is False or raw_book.get("suspended") is True:
                    continue
                offers = self._parse_bookmaker_markets(
                    normalized_bookmaker, raw_book.get("markets") or {}, market_catalog
                )
                if offers:
                    bookmakers.append(
                        Bookmaker(
                            key=normalized_bookmaker,
                            title=self._bookmaker_title(str(bookmaker_key)),
                            markets=offers,
                            last_update=last_update,
                        )
                    )

            if bookmakers:
                events.append(
                    Event(
                        id=fixture_id,
                        sport_key="americanfootball_nfl",
                        sport_title="NFL",
                        commence_time=commence_time,
                        home_team=home_team,
                        away_team=away_team,
                        home_team_canonical=TeamNormalizer.canonical_team(home_team),
                        away_team_canonical=TeamNormalizer.canonical_team(away_team),
                        bookmakers=bookmakers,
                    )
                )
        return events

    def _parse_bookmaker_markets(
        self,
        bookmaker_key: str,
        raw_markets: Any,
        market_catalog: dict[str, dict[str, Any]],
    ) -> list[MarketOffer]:
        if not isinstance(raw_markets, dict):
            return []

        grouped: dict[tuple[str, str, float | None, str], list[MarketOutcome]] = {}
        for market_id, raw_market in raw_markets.items():
            if not isinstance(raw_market, dict) or raw_market.get("marketActive") is False:
                continue
            metadata = market_catalog.get(str(market_id), {})
            market_key = metadata.get("canonical_key") or self._infer_market_key(raw_market)
            if not market_key:
                continue
            market_name = str(metadata.get("market_name") or market_key.replace("_", " ").title())
            outcome_names = metadata.get("outcomes") or {}
            catalog_point = self._to_float(metadata.get("handicap"))

            raw_outcomes = raw_market.get("outcomes") or {}
            if not isinstance(raw_outcomes, dict):
                continue
            for outcome_id, raw_outcome in raw_outcomes.items():
                if not isinstance(raw_outcome, dict):
                    continue
                players = raw_outcome.get("players") or {}
                if not isinstance(players, dict):
                    continue
                for player_id, raw_price in players.items():
                    if not isinstance(raw_price, dict) or raw_price.get("active") is False:
                        continue
                    price = self._to_float(raw_price.get("price"))
                    if price is None or price <= 1.0:
                        continue

                    provider_label = str(
                        raw_price.get("bookmakerOutcomeId")
                        or outcome_names.get(str(outcome_id))
                        or outcome_id
                    )
                    outcome_label = str(outcome_names.get(str(outcome_id)) or provider_label)
                    player_name = self._display_player_name(raw_price.get("playerName"))
                    player_canonical = PlayerNameNormalizer.clean_name(player_name) if player_name else ""
                    point = self._first_number(
                        raw_price.get("handicap"),
                        raw_price.get("total"),
                        raw_price.get("line"),
                        catalog_point,
                        self._line_from_label(provider_label),
                    )
                    if market_key == "player_anytime_td" and point is None:
                        point = 0.5
                    outcome_type = self._outcome_type(outcome_label, provider_label)

                    group_key = (market_key, player_canonical, point, market_name)
                    grouped.setdefault(group_key, []).append(
                        MarketOutcome(
                            name=outcome_type.value.title(),
                            point=point,
                            odds=OddsValue.from_decimal(price),
                            player_id=None if str(player_id) == "0" else str(player_id),
                            player_name=player_name,
                            player_canonical=player_canonical or None,
                            outcome_type=outcome_type,
                            metadata={
                                "oddspapi_market_id": str(market_id),
                                "oddspapi_outcome_id": str(outcome_id),
                                "main_line": bool(raw_price.get("mainLine")),
                                "limit": raw_price.get("limit"),
                            },
                        )
                    )

        offers: list[MarketOffer] = []
        for (market_key, player_canonical, point, market_name), outcomes in grouped.items():
            player_name = next((item.player_name for item in outcomes if item.player_name), None)
            offers.append(
                MarketOffer(
                    market_key=market_key,
                    market_type=market_key,
                    label=f"{player_name} - {market_name}" if player_name else market_name,
                    player_name=player_name,
                    player_canonical=player_canonical or None,
                    point=point,
                    outcomes=outcomes,
                    bookmaker=bookmaker_key,
                )
            )
        return offers

    @staticmethod
    def _infer_market_key(raw_market: dict[str, Any]) -> str | None:
        text = str(raw_market.get("bookmakerMarketId") or "").lower()
        if "moneyline" in text or "winner" in text:
            return "h2h"
        if "handicap" in text or "spread" in text:
            return "spreads"
        if "total" in text:
            return "totals"
        return None

    @staticmethod
    def _outcome_type(*labels: str) -> OutcomeType:
        normalized = [str(label).lower().strip() for label in labels]
        text = " ".join(normalized)
        if "over" in text:
            return OutcomeType.OVER
        if "under" in text:
            return OutcomeType.UNDER
        if any(label == "1" or "home" in label for label in normalized):
            return OutcomeType.HOME
        if any(label == "2" or "away" in label for label in normalized):
            return OutcomeType.AWAY
        if any(label == "x" or "draw" in label for label in normalized):
            return OutcomeType.DRAW
        if "yes" in text:
            return OutcomeType.YES
        if "no" in text:
            return OutcomeType.NO
        return OutcomeType.YES

    @staticmethod
    def _line_from_label(label: str) -> float | None:
        match = re.search(r"(?<!\d)([+-]?\d+(?:\.\d+)?)", label)
        return float(match.group(1)) if match else None

    @classmethod
    def _first_number(cls, *values: Any) -> float | None:
        for value in values:
            converted = cls._to_float(value)
            if converted is not None:
                return converted
        return None

    @staticmethod
    def _to_float(value: Any) -> float | None:
        try:
            return float(value) if value is not None else None
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _display_player_name(value: Any) -> str | None:
        if not value:
            return None
        name = str(value).strip()
        if "," in name:
            last, first = (part.strip() for part in name.split(",", 1))
            if first and last:
                return f"{first} {last}"
        return name

    @staticmethod
    def _parse_timestamp(value: Any, default_now: bool = True) -> datetime | None:
        if isinstance(value, str):
            try:
                return datetime.fromisoformat(value.replace("Z", "+00:00"))
            except ValueError:
                pass
        return datetime.now(timezone.utc) if default_now else None

    @staticmethod
    def _bookmaker_title(key: str) -> str:
        titles = {"bet365": "Bet365", "pinnacle": "Pinnacle", "circa": "Circa Sports"}
        return titles.get(key.lower(), key.replace("_", " ").title())

    def _extract_rate_limits(self, headers: Any) -> None:
        for header in ("x-requests-remaining", "x-ratelimit-remaining"):
            if header in headers:
                try:
                    self.remaining_requests = int(headers[header])
                except (TypeError, ValueError):
                    pass
        for header in ("x-requests-used", "x-ratelimit-used"):
            if header in headers:
                try:
                    self.used_requests = int(headers[header])
                except (TypeError, ValueError):
                    pass

    def load_mock_snapshot(self) -> list[Event]:
        """Use the existing offline snapshot without consuming API credits."""
        sample_path = Path(__file__).resolve().parent.parent.parent / "sample_data" / "odds_snapshot_sample.json"
        if sample_path.exists():
            try:
                from app.adapters.csv_odds_adapter import CSVOddsAdapter

                return CSVOddsAdapter().parse_payload(sample_path.read_text(encoding="utf-8"))
            except Exception as exc:
                logger.warning("Could not parse the offline odds snapshot: %s", exc)
        return []
