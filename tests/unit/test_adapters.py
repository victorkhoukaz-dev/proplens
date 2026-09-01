"""
Unit tests for app.adapters: TheOddsAPIAdapter, CSVOddsAdapter, and BaseOddsAdapter.
Verifies parsing of live/offline JSON payloads, CSV/TSV/Pipe/Clipboard odds tables,
wide vs long format parsing, rate limit tracking, and mock snapshot fallback.
"""

from pathlib import Path
import pytest

from app.adapters.the_odds_api import (
    OddsAPIQuotaExceededError,
    TheOddsAPIAdapter,
)
from app.adapters.oddspapi_adapter import OddsPapiAdapter
from app.db.raw_odds_snapshot_store import RawOddsSnapshotStore
from app.adapters.csv_odds_adapter import CSVOddsAdapter
from app.schemas.odds import Event, MarketOffer, MarketOutcome, OddsValue, OutcomeType


class TestTheOddsAPIAdapter:
    """Test suite for TheOddsAPI v4 ingestion adapter."""

    @pytest.fixture
    def adapter(self):
        sample_path = Path(__file__).resolve().parent.parent.parent / "sample_data" / "odds_snapshot_sample.json"
        return TheOddsAPIAdapter(api_key="MOCK", sample_data_path=sample_path)

    @pytest.mark.asyncio
    async def test_fetch_odds_mock_fallback(self, adapter):
        events = await adapter.fetch_odds()
        assert len(events) > 0
        event = events[0]

        assert isinstance(event, Event)
        assert event.id == "e9b28a8d110f4439a0fa0e1819bc5a11"
        assert event.home_team == "Buffalo Bills"
        assert event.away_team == "Kansas City Chiefs"
        assert event.home_team_canonical == "BUF"
        assert event.away_team_canonical == "KC"
        assert event.game_title == "KC @ BUF"

        # Check bookmakers
        bet365 = event.get_bookmaker("bet365")
        assert bet365 is not None
        assert bet365.key == "bet365"

        pinnacle = event.get_bookmaker("pinnacle")
        assert pinnacle is not None
        assert pinnacle.key == "pinnacle"

        circa = event.get_bookmaker("circa")
        assert circa is not None

        # Check markets in bet365
        h2h = bet365.get_market("h2h")
        assert h2h is not None
        assert len(h2h.outcomes) == 2

        pass_yds = bet365.get_market("player_pass_yds")
        assert pass_yds is not None
        assert len(pass_yds.outcomes) >= 2

        mahomes_over = pass_yds.get_outcome("over")
        assert mahomes_over is not None
        assert mahomes_over.player_canonical == "patrick mahomes"
        assert mahomes_over.odds.decimal == 1.91

    def test_rate_limit_extraction(self, adapter):
        headers = {
            "x-requests-remaining": "450",
            "x-requests-used": "50",
            "x-requests-last": "2",
        }
        adapter._extract_rate_limits(headers)
        assert adapter.remaining_requests == 450
        assert adapter.used_requests == 50
        assert adapter.last_request_cost == 2

    def test_parse_payload_direct_json_dict_and_list(self, adapter):
        sample_dict = {
            "id": "event_single",
            "sport_key": "americanfootball_nfl",
            "home_team": "Miami Dolphins",
            "away_team": "New York Jets",
            "bookmakers": [
                {
                    "key": "bet365_us",
                    "title": "Bet365",
                    "markets": [
                        {
                            "key": "totals",
                            "outcomes": [
                                {"name": "Over", "price": 1.91, "point": 44.5},
                                {"name": "Under", "price": 1.91, "point": 44.5},
                            ],
                        }
                    ],
                }
            ],
        }

        events = adapter.parse_payload(sample_dict)
        assert len(events) == 1
        assert events[0].id == "event_single"
        assert events[0].home_team_canonical == "MIA"
        assert events[0].away_team_canonical == "NYJ"
        assert events[0].bookmakers[0].key == "bet365"


class TestOddsPapiAdapter:
    """Tests the official OddsPapi NFL response shape without network calls."""

    @staticmethod
    def market_catalog_payload():
        return [
            {
                "marketId": 141,
                "marketName": "Winner (incl. overtime)",
                "marketType": "moneyline",
                "playerProp": False,
                "outcomes": [
                    {"outcomeId": 141, "outcomeName": "1"},
                    {"outcomeId": 142, "outcomeName": "2"},
                ],
            },
            {
                "marketId": 15001,
                "marketName": "Player Passing Yards",
                "marketType": "totals",
                "playerProp": True,
                "outcomes": [
                    {"outcomeId": 15001, "outcomeName": "Over"},
                    {"outcomeId": 15002, "outcomeName": "Under"},
                ],
            },
        ]

    @staticmethod
    def odds_payload():
        def book(over_price, under_price):
            return {
                "bookmakerIsActive": True,
                "suspended": False,
                "markets": {
                    "15001": {
                        "marketActive": True,
                        "outcomes": {
                            "15001": {
                                "players": {
                                    "100": {
                                        "active": True,
                                        "bookmakerOutcomeId": "265.5/over",
                                        "playerName": "Mahomes, Patrick",
                                        "price": over_price,
                                        "mainLine": True,
                                    }
                                }
                            },
                            "15002": {
                                "players": {
                                    "100": {
                                        "active": True,
                                        "bookmakerOutcomeId": "265.5/under",
                                        "playerName": "Mahomes, Patrick",
                                        "price": under_price,
                                        "mainLine": True,
                                    }
                                }
                            },
                        },
                    }
                },
            }

        return [
            {
                "fixtureId": "id1400003171515752",
                "sportId": 14,
                "tournamentId": 31,
                "participant1Name": "Kansas City Chiefs",
                "participant2Name": "Buffalo Bills",
                "startTime": "2026-09-10T20:00:00.000Z",
                "updatedAt": "2026-08-14T20:00:00.000Z",
                "bookmakerOdds": {
                    "bet365": book(1.91, 1.91),
                    "pinnacle": book(1.95, 1.87),
                },
            }
        ]

    def test_parses_dynamic_nfl_player_prop_for_both_books(self):
        adapter = OddsPapiAdapter(api_key="MOCK")
        catalog = adapter.build_market_catalog(self.market_catalog_payload())
        events = adapter.parse_fixtures(self.odds_payload(), catalog)

        assert len(events) == 1
        event = events[0]
        assert event.home_team_canonical == "KC"
        assert event.away_team_canonical == "BUF"
        assert {book.key for book in event.bookmakers} == {"bet365", "pinnacle"}

        offer = event.get_bookmaker("bet365").get_market(
            "player_pass_yds", player_name="Patrick Mahomes"
        )
        assert offer is not None
        assert offer.point == 265.5
        assert offer.player_canonical == "patrick mahomes"
        assert [outcome.outcome_type.value for outcome in offer.outcomes] == ["over", "under"]

    @pytest.mark.asyncio
    async def test_live_fetch_uses_official_nfl_ids_and_combined_bookmakers(self, monkeypatch, tmp_path):
        OddsPapiAdapter._market_catalog_cache = None
        calls = []
        market_payload = self.market_catalog_payload()
        odds_payload = self.odds_payload()

        class FakeResponse:
            def __init__(self, payload):
                self.status_code = 200
                self.headers = {}
                self._payload = payload

            def json(self):
                return self._payload

            def raise_for_status(self):
                return None

        class FakeClient:
            def __init__(self, **kwargs):
                self.kwargs = kwargs

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                return None

            async def get(self, url, params):
                calls.append((url, params))
                payload = market_payload if url.endswith("/markets") else odds_payload
                return FakeResponse(payload)

        monkeypatch.setattr("app.adapters.oddspapi_adapter.httpx.AsyncClient", FakeClient)
        adapter = OddsPapiAdapter(
            api_key="test-key",
            mock_fallback=False,
            request_spacing_seconds=0,
            raw_snapshot_store=RawOddsSnapshotStore(tmp_path / "raw"),
        )
        events = await adapter.fetch_odds()

        assert len(events) == 1
        assert {book.key for book in events[0].bookmakers} == {"bet365", "pinnacle"}
        assert len(calls) == 3
        assert calls[0][1]["sportId"] == 14
        assert calls[1][1]["tournamentIds"] == "31"
        assert calls[1][1]["bookmaker"] == "bet365"
        assert calls[2][1]["bookmaker"] == "pinnacle"
        assert "bookmakers" not in calls[1][1]
        assert adapter.last_raw_snapshot_path is not None
        assert Path(adapter.last_raw_snapshot_path).exists()
        assert "test-key" not in Path(adapter.last_raw_snapshot_path).read_text(encoding="utf-8")

    def test_bad_request_message_does_not_expose_request_url(self):
        class FakeResponse:
            status_code = 400

            @staticmethod
            def json():
                return {"message": "Invalid bookmaker filter"}

        with pytest.raises(RuntimeError) as error:
            OddsPapiAdapter._raise_for_api_error(FakeResponse(), "NFL odds")

        assert "Invalid bookmaker filter" in str(error.value)
        assert "apiKey" not in str(error.value)
        assert "http" not in str(error.value)

    def test_numeric_bookmaker_ids_do_not_override_catalog_lines_or_outcomes(self):
        assert OddsPapiAdapter._outcome_type("1", "1626638753") == OutcomeType.HOME
        assert OddsPapiAdapter._outcome_type("2", "1626638754") == OutcomeType.AWAY
        assert OddsPapiAdapter._first_number(None, None, None, -3.5, 1626638753.0) == -3.5


class TestCSVOddsAdapter:
    """Test suite for CSVOddsAdapter."""

    @pytest.fixture
    def csv_adapter(self):
        return CSVOddsAdapter()

    def test_sniff_delimiters(self, csv_adapter):
        csv_text = "Player,Team,Line\nPatrick Mahomes,KC,268.5"
        tsv_text = "Player\tTeam\tLine\nPatrick Mahomes\tKC\t268.5"
        pipe_text = "Player | Team | Line\nPatrick Mahomes | KC | 268.5"
        semi_text = "Player;Team;Line\nPatrick Mahomes;KC;268.5"

        assert csv_adapter._sniff_delimiter(csv_text) == ","
        assert csv_adapter._sniff_delimiter(tsv_text) == "\t"
        assert csv_adapter._sniff_delimiter(pipe_text) == "|"
        assert csv_adapter._sniff_delimiter(semi_text) == ";"

    def test_parse_wide_csv_odds(self, csv_adapter):
        csv_data = """Player,Team,Market,Line,Over,Under,Bookmaker
Patrick Mahomes,KC,Pass Yds,268.5,-110,-110,Bet365
Josh Allen,BUF,Pass Yds,242.5,-115,-105,Pinnacle
Travis Kelce,KC,Rec Yds,62.5,-110,-110,Bet365
"""
        events = csv_adapter.parse_payload(csv_data)
        assert len(events) >= 2  # KC and BUF events

        kc_event = next(e for e in events if e.home_team_canonical == "KC")
        assert kc_event is not None
        bet365 = kc_event.get_bookmaker("bet365")
        assert bet365 is not None

        pass_yds = bet365.get_market("player_pass_yds", player_name="Patrick Mahomes")
        assert pass_yds is not None
        assert pass_yds.point == 268.5
        assert len(pass_yds.outcomes) == 2
        assert pass_yds.outcomes[0].odds.american == -110

    def test_parse_long_csv_odds(self, csv_adapter):
        csv_data = """Player,Team,Market,Line,Side,Odds,Bookmaker
Patrick Mahomes,KC,Pass Yds,268.5,Over,-110,Bet365
Patrick Mahomes,KC,Pass Yds,268.5,Under,-110,Bet365
Isiah Pacheco,KC,Anytime TD,0.5,Yes,+120,Bet365
"""
        events = csv_adapter.parse_payload(csv_data)
        assert len(events) == 1
        event = events[0]
        bet365 = event.get_bookmaker("bet365")
        assert bet365 is not None

        pass_yds = bet365.get_market("player_pass_yds", player_name="Patrick Mahomes")
        assert pass_yds is not None
        assert len(pass_yds.outcomes) == 2

        atd = bet365.get_market("player_anytime_td", player_name="Isiah Pacheco")
        assert atd is not None
        assert len(atd.outcomes) == 1
        assert atd.outcomes[0].odds.american == 120

    def test_header_synonym_resolution(self, csv_adapter):
        tsv_data = """Athlete\tMatchup\tProp\tPoint\tOver Price\tUnder Price\tSportsbook
Marvin Harrison Jr.\tARI\tReceiving Yards\t67.5\t-110\t-110\tDraftKings
"""
        events = csv_adapter.parse_payload(tsv_data)
        assert len(events) == 1
        event = events[0]
        assert event.home_team_canonical == "ARI"
        dk = event.get_bookmaker("draftkings")
        assert dk is not None

        rec_yds = dk.get_market("player_rec_yds", player_name="Marvin Harrison Jr.")
        assert rec_yds is not None
        assert rec_yds.point == 67.5
        assert len(rec_yds.outcomes) == 2

    def test_sample_csv_file_parsing(self, csv_adapter):
        csv_path = Path(__file__).resolve().parent.parent.parent / "sample_data" / "odds_sample.csv"
        events = csv_adapter.parse_payload(csv_path)
        assert len(events) > 0

    def test_empty_payload_handling(self, csv_adapter):
        assert csv_adapter.parse_payload("") == []
        assert csv_adapter.parse_payload("   \n\n  ") == []
