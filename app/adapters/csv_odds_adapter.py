"""
Universal CSV, TSV, Pipe-Delimited, and JSON Clipboard Odds Ingestion Adapter.
NFL +EV Betting Application (Bet365 Canada vs. Sharp Devig & FantasyPoints).
"""

from __future__ import annotations

import csv
import io
import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

from app.adapters.base import BaseOddsAdapter
from app.core.normalizer import PlayerNameNormalizer, TeamNormalizer
from app.schemas.odds import Bookmaker, Event, MarketOffer, MarketOutcome, OddsValue, OutcomeType


logger = logging.getLogger(__name__)


class CSVOddsAdapter(BaseOddsAdapter):
    """
    Universal offline odds parser supporting CSV, TSV, pipe-delimited tables,
    and pasted text snapshots from spreadsheets or web interfaces.
    """

    # Synonym dictionaries for column mapping
    PLAYER_SYNONYMS = {"player", "player_name", "athlete", "name", "player_id", "passer", "rusher", "receiver"}
    TEAM_SYNONYMS = {"team", "player_team", "tm", "matchup", "game", "event", "home_team", "away_team"}
    MARKET_SYNONYMS = {"market", "prop", "stat", "market_key", "category", "stat_type", "prop_type", "type"}
    LINE_SYNONYMS = {"line", "point", "total", "over_under", "ou_line", "val", "target", "handicap"}
    OVER_ODDS_SYNONYMS = {"over", "over_odds", "over_price", "over_american", "over_dec", "over_decimal", "price_over", "o_odds"}
    UNDER_ODDS_SYNONYMS = {"under", "under_odds", "under_price", "under_american", "under_dec", "under_decimal", "price_under", "u_odds"}
    PRICE_SYNONYMS = {"odds", "price", "american", "decimal", "moneyline", "ml", "line_odds", "payout"}
    SIDE_SYNONYMS = {"side", "outcome", "pick", "direction", "choice", "selection"}
    BOOKMAKER_SYNONYMS = {"book", "bookmaker", "sportsbook", "source", "site", "feed"}

    # Market canonicalization dictionary
    MARKET_MAPPINGS = {
        "pass yds": "player_pass_yds",
        "pass yards": "player_pass_yds",
        "passing yds": "player_pass_yds",
        "passing yards": "player_pass_yds",
        "player_pass_yds": "player_pass_yds",
        "pass td": "player_pass_tds",
        "pass tds": "player_pass_tds",
        "passing td": "player_pass_tds",
        "passing tds": "player_pass_tds",
        "passing touchdowns": "player_pass_tds",
        "player_pass_tds": "player_pass_tds",
        "rush yds": "player_rush_yds",
        "rush yards": "player_rush_yds",
        "rushing yds": "player_rush_yds",
        "rushing yards": "player_rush_yds",
        "player_rush_yds": "player_rush_yds",
        "rush td": "player_rush_tds",
        "rush tds": "player_rush_tds",
        "rec yds": "player_rec_yds",
        "rec yards": "player_rec_yds",
        "receiving yds": "player_rec_yds",
        "receiving yards": "player_rec_yds",
        "player_rec_yds": "player_rec_yds",
        "receptions": "player_receptions",
        "rec": "player_receptions",
        "recs": "player_receptions",
        "player_receptions": "player_receptions",
        "anytime td": "player_anytime_td",
        "anytime touchdown": "player_anytime_td",
        "atd": "player_anytime_td",
        "td": "player_anytime_td",
        "player_anytime_td": "player_anytime_td",
        "interceptions": "player_pass_interceptions",
        "pass ints": "player_pass_interceptions",
        "int": "player_pass_interceptions",
        "ints": "player_pass_interceptions",
        "player_pass_interceptions": "player_pass_interceptions",
        "moneyline": "h2h",
        "h2h": "h2h",
        "ml": "h2h",
        "spread": "spreads",
        "spreads": "spreads",
        "point spread": "spreads",
        "totals": "totals",
        "total": "totals",
        "game total": "totals",
        "over/under": "totals",
    }

    def __init__(self) -> None:
        super().__init__(name="CSVOddsAdapter", is_live=False)

    async def fetch_odds(self, **kwargs: Any) -> list[Event]:
        """Fetch odds from file or string passed in kwargs."""
        source = kwargs.get("source")
        if not source:
            raise ValueError("CSVOddsAdapter.fetch_odds requires a 'source' parameter (file path, text, or bytes).")
        return self.parse_payload(source)

    def parse_payload(self, data: Any) -> list[Event]:
        """Parse CSV/TSV/Pipe text, file path, bytes, or JSON string into Events."""
        if isinstance(data, (Path, str)) and Path(str(data)).is_file():
            with open(str(data), "r", encoding="utf-8") as f:
                content = f.read()
            return self._parse_text(content)
        elif isinstance(data, bytes):
            return self._parse_text(data.decode("utf-8", errors="replace"))
        elif isinstance(data, str):
            return self._parse_text(data)
        elif isinstance(data, (dict, list)):
            from app.adapters.the_odds_api import TheOddsAPIAdapter
            return TheOddsAPIAdapter().parse_payload(data)
        else:
            raise TypeError(f"Unsupported data type for CSVOddsAdapter: {type(data)}")

    def _parse_text(self, text: str) -> list[Event]:
        """Auto-detect format and parse string text."""
        trimmed = text.strip()
        if not trimmed:
            return []

        # If it looks like JSON
        if (trimmed.startswith("{") and trimmed.endswith("}")) or (trimmed.startswith("[") and trimmed.endswith("]")):
            try:
                json_data = json.loads(trimmed)
                from app.adapters.the_odds_api import TheOddsAPIAdapter
                return TheOddsAPIAdapter().parse_payload(json_data)
            except Exception:
                pass  # Fall through to tabular parser

        # Tabular delimited parsing
        delimiter = self._sniff_delimiter(trimmed)
        lines = [line.strip() for line in trimmed.splitlines() if line.strip()]
        if not lines:
            return []

        reader = csv.reader(lines, delimiter=delimiter)
        raw_rows = list(reader)
        if not raw_rows:
            return []

        header_row = [h.strip().lower() for h in raw_rows[0]]
        col_map = self._resolve_column_indices(header_row)

        if not col_map or ("over" not in col_map and "under" not in col_map and "price" not in col_map):
            unheadered = self._parse_unheadered_lines(lines)
            if unheadered:
                return unheadered

        data_rows = raw_rows[1:]
        events_dict: dict[str, Event] = {}

        is_wide_format = ("over" in col_map) and ("under" in col_map)

        for row in data_rows:
            if not row or all(not cell.strip() for cell in row):
                continue
            try:
                if is_wide_format:
                    self._process_wide_row(row, col_map, events_dict)
                else:
                    self._process_long_row(row, col_map, events_dict)
            except Exception as e:
                logger.warning(f"Error parsing row {row}: {e}")

        parsed_events = self._validate_events(list(events_dict.values()))
        if not parsed_events:
            unheadered = self._parse_unheadered_lines(lines)
            if unheadered:
                return unheadered
        return parsed_events


    def _sniff_delimiter(self, text: str) -> str:
        """Sniff delimiter from first 5 lines."""
        sample_lines = [l for l in text.splitlines() if l.strip()][:5]
        sample = "\n".join(sample_lines)

        counts = {
            "\t": sample.count("\t"),
            ",": sample.count(","),
            "|": sample.count("|"),
            ";": sample.count(";"),
        }
        best_delim = max(counts, key=counts.get)  # type: ignore[arg-type]
        if counts[best_delim] > 0:
            return best_delim
        return ","

    def _resolve_column_indices(self, headers: list[str]) -> dict[str, int]:
        """Map canonical roles to column indices using synonym sets."""
        col_map: dict[str, int] = {}
        for idx, h in enumerate(headers):
            clean_h = re.sub(r"[^\w\s]", "", h).strip().lower().replace(" ", "_")

            if clean_h in self.PLAYER_SYNONYMS or any(s in clean_h for s in ("player", "athlete", "passer", "rusher", "receiver")):
                if "player" not in col_map:
                    col_map["player"] = idx
            elif clean_h in self.TEAM_SYNONYMS or clean_h in ("team", "tm", "matchup", "game"):
                if "team" not in col_map:
                    col_map["team"] = idx
            elif clean_h in self.MARKET_SYNONYMS or clean_h in ("market", "prop", "stat", "category"):
                if "market" not in col_map:
                    col_map["market"] = idx
            elif clean_h in self.LINE_SYNONYMS or clean_h in ("line", "point", "total", "ou"):
                if "line" not in col_map:
                    col_map["line"] = idx
            elif clean_h in self.OVER_ODDS_SYNONYMS or clean_h.startswith("over") or clean_h == "o":
                if "over" not in col_map:
                    col_map["over"] = idx
            elif clean_h in self.UNDER_ODDS_SYNONYMS or clean_h.startswith("under") or clean_h == "u":
                if "under" not in col_map:
                    col_map["under"] = idx
            elif clean_h in self.PRICE_SYNONYMS or clean_h in ("odds", "price", "american", "decimal", "payout"):
                if "odds" not in col_map:
                    col_map["odds"] = idx
            elif clean_h in self.SIDE_SYNONYMS or clean_h in ("side", "outcome", "pick", "selection"):
                if "side" not in col_map:
                    col_map["side"] = idx
            elif clean_h in self.BOOKMAKER_SYNONYMS or clean_h in ("book", "bookmaker", "sportsbook", "source", "site"):
                if "bookmaker" not in col_map:
                    col_map["bookmaker"] = idx
        return col_map

    def _parse_odds_cell(self, raw_val: str) -> OddsValue | None:
        """Parse raw cell string into OddsValue."""
        if not raw_val:
            return None
        cleaned = raw_val.strip().replace("$", "").replace(" ", "")
        if not cleaned:
            return None

        try:
            val_float = float(cleaned)
            if abs(val_float) >= 100 or ("+" in cleaned or (cleaned.startswith("-") and not (1.0 < abs(val_float) < 100))):
                return OddsValue.from_american(int(round(val_float)))
            elif val_float > 1.0:
                return OddsValue.from_decimal(val_float)
        except Exception:
            return None
        return None

    def _canonicalize_market(self, raw_market: str) -> str:
        """Normalize market string to canonical key."""
        clean = raw_market.strip().lower().replace("_", " ").replace("-", " ")
        if clean in self.MARKET_MAPPINGS:
            return self.MARKET_MAPPINGS[clean]
        for k, v in self.MARKET_MAPPINGS.items():
            if k in clean:
                return v
        return raw_market.strip().lower().replace(" ", "_")

    def _parse_unheadered_lines(self, lines: Sequence[str]) -> list[Event]:
        """Parse raw text lines from clipboard or web dumps without CSV headers."""
        active_market = "player_pass_yds"
        active_game = "NFL Slate"
        market_offers: list[MarketOffer] = []

        two_way_regex = re.compile(
            r"^([A-Za-z\s\.\'\-]+?)\s+(\d+\.?\d*)\s+([+-]?\d{3,4}|\d+\.\d{2})\s+([+-]?\d{3,4}|\d+\.\d{2})$"
        )

        for line in lines:
            line_str = line.strip()
            if not line_str:
                continue

            if "@" in line_str or " vs " in line_str.lower():
                active_game = line_str
                continue

            clean_hdr = line_str.lower().replace("_", " ").replace("-", " ")
            if clean_hdr in self.MARKET_MAPPINGS:
                active_market = self.MARKET_MAPPINGS[clean_hdr]
                continue

            tokens = [t.strip() for t in re.split(r"\t+|\s{2,}", line_str) if t.strip()]
            if len(tokens) >= 4 and not re.match(r"^\d", tokens[0]):
                p_name = tokens[0]
                try:
                    p_line = float(tokens[1])
                    o_odds = self._parse_odds_cell(tokens[2])
                    u_odds = self._parse_odds_cell(tokens[3])
                    if o_odds and u_odds and not re.match(r"^(over|under|total|spread)$", p_name.strip(), re.I):
                        clean_player = PlayerNameNormalizer.clean_name(p_name)
                        outcomes = [
                            MarketOutcome(name=f"{p_name} Over", point=p_line, odds=o_odds, player_name=p_name, player_canonical=clean_player, outcome_type=OutcomeType.OVER),
                            MarketOutcome(name=f"{p_name} Under", point=p_line, odds=u_odds, player_name=p_name, player_canonical=clean_player, outcome_type=OutcomeType.UNDER),
                        ]
                        offer = MarketOffer(
                            market_key=active_market,
                            label=f"{p_name} - {active_market}",
                            player_name=p_name,
                            player_canonical=clean_player,
                            point=p_line,
                            outcomes=outcomes,
                            bookmaker="bet365",
                        )
                        market_offers.append(offer)
                        continue
                except ValueError:
                    pass

            m2 = two_way_regex.match(line_str)
            if m2:
                p_name, raw_line, raw_over, raw_under = m2.groups()
                o_odds = self._parse_odds_cell(raw_over)
                u_odds = self._parse_odds_cell(raw_under)
                if o_odds and u_odds and not re.match(r"^(over|under|total|spread)$", p_name.strip(), re.I):
                    clean_player = PlayerNameNormalizer.clean_name(p_name.strip())
                    p_line = float(raw_line)
                    outcomes = [
                        MarketOutcome(name=f"{p_name.strip()} Over", point=p_line, odds=o_odds, player_name=p_name.strip(), player_canonical=clean_player, outcome_type=OutcomeType.OVER),
                        MarketOutcome(name=f"{p_name.strip()} Under", point=p_line, odds=u_odds, player_name=p_name.strip(), player_canonical=clean_player, outcome_type=OutcomeType.UNDER),
                    ]
                    offer = MarketOffer(
                        market_key=active_market,
                        label=f"{p_name.strip()} - {active_market}",
                        player_name=p_name.strip(),
                        player_canonical=clean_player,
                        point=p_line,
                        outcomes=outcomes,
                        bookmaker="bet365",
                    )
                    market_offers.append(offer)
                    continue

        if not market_offers:
            return []

        home_t = "NFL Home"
        away_t = "NFL Away"
        if "@" in active_game:
            parts = active_game.split("@")
            away_t = TeamNormalizer.canonical_team(parts[0].strip())
            home_t = TeamNormalizer.canonical_team(parts[1].strip())

        ev_obj = Event(
            id=f"event_bet365_unheadered_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}",
            sport_key="americanfootball_nfl",
            sport_title="NFL",
            home_team=home_t,
            away_team=away_t,
            commence_time=datetime.now(timezone.utc),
            bookmakers=[Bookmaker(key="bet365", title="Bet365", markets=market_offers)],
        )
        return [ev_obj]


    def _get_or_create_event_and_book(
        self,
        raw_team: str,
        raw_book: str,
        events_dict: dict[str, Event],
    ) -> tuple[Event, Bookmaker]:
        """Retrieve or construct the Event and Bookmaker container."""
        team_canon = TeamNormalizer.canonical_team(raw_team) if raw_team else "NFL"
        bm_key = raw_book.strip().lower() if raw_book else "bet365"
        if bm_key.startswith("bet365"):
            bm_key = "bet365"
        elif bm_key in ("circa", "circasports"):
            bm_key = "circa"

        event_id = f"event_{team_canon}"
        if event_id not in events_dict:
            events_dict[event_id] = Event(
                id=event_id,
                commence_time=datetime.now(timezone.utc),
                home_team=team_canon,
                away_team="OPP",
                home_team_canonical=team_canon,
                away_team_canonical="OPP",
                bookmakers=[],
            )

        event = events_dict[event_id]
        bookmaker = event.get_bookmaker(bm_key)
        if not bookmaker:
            bookmaker = Bookmaker(
                key=bm_key,
                title=bm_key.title(),
                markets=[],
            )
            event.bookmakers.append(bookmaker)

        return event, bookmaker

    def _process_wide_row(
        self,
        row: list[str],
        col_map: dict[str, int],
        events_dict: dict[str, Event],
    ) -> None:
        """Process a wide table row containing both Over and Under odds."""
        player_raw = row[col_map["player"]].strip() if "player" in col_map and col_map["player"] < len(row) else None
        team_raw = row[col_map["team"]].strip() if "team" in col_map and col_map["team"] < len(row) else ""
        market_raw = row[col_map["market"]].strip() if "market" in col_map and col_map["market"] < len(row) else "player_prop"
        line_raw = row[col_map["line"]].strip() if "line" in col_map and col_map["line"] < len(row) else None
        over_raw = row[col_map["over"]].strip() if "over" in col_map and col_map["over"] < len(row) else ""
        under_raw = row[col_map["under"]].strip() if "under" in col_map and col_map["under"] < len(row) else ""
        book_raw = row[col_map["bookmaker"]].strip() if "bookmaker" in col_map and col_map["bookmaker"] < len(row) else "bet365"

        over_odds = self._parse_odds_cell(over_raw)
        under_odds = self._parse_odds_cell(under_raw)

        if not over_odds and not under_odds:
            return

        point = float(line_raw) if line_raw else None
        market_key = self._canonicalize_market(market_raw)
        player_canonical = PlayerNameNormalizer.clean_name(player_raw) if player_raw else None

        _, bookmaker = self._get_or_create_event_and_book(team_raw, book_raw, events_dict)

        outcomes: list[MarketOutcome] = []
        if over_odds:
            outcomes.append(MarketOutcome(
                name="Over",
                point=point,
                odds=over_odds,
                outcome_type="over",
                player_name=player_raw,
                player_canonical=player_canonical,
            ))
        if under_odds:
            outcomes.append(MarketOutcome(
                name="Under",
                point=point,
                odds=under_odds,
                outcome_type="under",
                player_name=player_raw,
                player_canonical=player_canonical,
            ))

        label = f"{player_raw} - {market_raw}" if player_raw else market_raw
        offer = MarketOffer(
            market_key=market_key,
            label=label,
            player_name=player_raw,
            player_canonical=player_canonical,
            point=point,
            bookmaker=bookmaker.key,
            outcomes=outcomes,
        )
        bookmaker.markets.append(offer)

    def _process_long_row(
        self,
        row: list[str],
        col_map: dict[str, int],
        events_dict: dict[str, Event],
    ) -> None:
        """Process a long table row containing a single outcome per row."""
        player_raw = row[col_map["player"]].strip() if "player" in col_map and col_map["player"] < len(row) else None
        team_raw = row[col_map["team"]].strip() if "team" in col_map and col_map["team"] < len(row) else ""
        market_raw = row[col_map["market"]].strip() if "market" in col_map and col_map["market"] < len(row) else "player_prop"
        line_raw = row[col_map["line"]].strip() if "line" in col_map and col_map["line"] < len(row) else None
        odds_raw = row[col_map["odds"]].strip() if "odds" in col_map and col_map["odds"] < len(row) else ""
        side_raw = row[col_map["side"]].strip() if "side" in col_map and col_map["side"] < len(row) else "Over"
        book_raw = row[col_map["bookmaker"]].strip() if "bookmaker" in col_map and col_map["bookmaker"] < len(row) else "bet365"

        odds = self._parse_odds_cell(odds_raw)
        if not odds:
            return

        point = float(line_raw) if line_raw else None
        market_key = self._canonicalize_market(market_raw)
        player_canonical = PlayerNameNormalizer.clean_name(player_raw) if player_raw else None

        _, bookmaker = self._get_or_create_event_and_book(team_raw, book_raw, events_dict)

        side_lower = side_raw.lower()
        if "over" in side_lower:
            outcome_type = "over"
        elif "under" in side_lower:
            outcome_type = "under"
        elif "yes" in side_lower:
            outcome_type = "yes"
        elif "no" in side_lower:
            outcome_type = "no"
        else:
            outcome_type = side_lower

        outcome = MarketOutcome(
            name=side_raw,
            point=point,
            odds=odds,
            outcome_type=outcome_type,
            player_name=player_raw,
            player_canonical=player_canonical,
        )

        label = f"{player_raw} - {market_raw}" if player_raw else market_raw
        existing_offer = bookmaker.get_market(market_key, player_name=player_raw)
        if existing_offer:
            existing_offer.outcomes.append(outcome)
        else:
            offer = MarketOffer(
                market_key=market_key,
                label=label,
                player_name=player_raw,
                player_canonical=player_canonical,
                point=point,
                bookmaker=bookmaker.key,
                outcomes=[outcome],
            )
            bookmaker.markets.append(offer)
