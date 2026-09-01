"""
Unit tests for Pydantic v2 core schemas: OddsValue, MarketOutcome, MarketOffer,
Bookmaker, Event, StatCategory, PlayerProjection, and EVResult.
"""

from datetime import datetime, timezone
import pytest

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


class TestOddsConversion:
    """Test suite for American and Decimal odds conversions."""

    def test_american_to_decimal_standard(self):
        assert american_to_decimal(100) == 2.0
        assert american_to_decimal(-100) == 2.0
        assert american_to_decimal(-110) == pytest.approx(1.909091, rel=1e-5)
        assert american_to_decimal(150) == 2.50
        assert american_to_decimal(200) == 3.00
        assert american_to_decimal(-200) == 1.50
        assert american_to_decimal(-10000) == 1.01
        assert american_to_decimal(99900) == 1000.0

    def test_american_to_decimal_invalid_range(self):
        with pytest.raises(ValueError, match="Invalid American odds"):
            american_to_decimal(0)
        with pytest.raises(ValueError, match="Invalid American odds"):
            american_to_decimal(50)
        with pytest.raises(ValueError, match="Invalid American odds"):
            american_to_decimal(-50)

    def test_decimal_to_american_standard(self):
        assert decimal_to_american(2.0) == 100
        assert decimal_to_american(2.5) == 150
        assert decimal_to_american(3.0) == 200
        assert decimal_to_american(1.909091) == -110
        assert decimal_to_american(1.50) == -200
        assert decimal_to_american(1.01) == -10000
        assert decimal_to_american(1000.0) == 99900

    def test_decimal_to_american_invalid(self):
        with pytest.raises(ValueError, match="Invalid Decimal odds"):
            decimal_to_american(1.0)
        with pytest.raises(ValueError, match="Invalid Decimal odds"):
            decimal_to_american(0.5)
        with pytest.raises(ValueError, match="Invalid Decimal odds"):
            decimal_to_american(-1.5)


class TestOddsValue:
    """Test suite for OddsValue Pydantic model."""

    def test_odds_value_from_american(self):
        odds = OddsValue.from_american(-110)
        assert odds.american == -110
        assert odds.decimal == pytest.approx(1.909091, rel=1e-5)
        assert odds.implied_probability == pytest.approx(0.52381, rel=1e-4)

    def test_odds_value_from_decimal(self):
        odds = OddsValue.from_decimal(2.50)
        assert odds.american == 150
        assert odds.decimal == 2.50
        assert odds.implied_probability == 0.40

    def test_odds_value_from_probability(self):
        odds = OddsValue.from_probability(0.50)
        assert odds.decimal == 2.0
        assert odds.american == 100

        with pytest.raises(ValueError, match="Probability must be strictly between 0 and 1"):
            OddsValue.from_probability(1.5)
        with pytest.raises(ValueError, match="Probability must be strictly between 0 and 1"):
            OddsValue.from_probability(0.0)

    def test_odds_value_immutability(self):
        odds = OddsValue.from_american(150)
        with pytest.raises(Exception):
            odds.american = 200  # type: ignore[misc]

    def test_odds_value_sync_tolerance(self):
        # Bookmaker slightly rounds -110 to 1.91 (diff < 0.025)
        odds = OddsValue(american=-110, decimal=1.91)
        assert odds.american == -110
        assert odds.decimal == pytest.approx(1.909091, rel=1e-4)


class TestMarketAndEventModels:
    """Test suite for MarketOffer, MarketOutcome, Bookmaker, and Event models."""

    def test_market_outcome_creation(self):
        odds = OddsValue.from_american(-110)
        outcome = MarketOutcome(
            name="Over",
            point=268.5,
            odds=odds,
            player_name="Patrick Mahomes",
            outcome_type=OutcomeType.OVER,
        )
        assert outcome.name == "Over"
        assert outcome.point == 268.5
        assert outcome.odds.american == -110
        assert outcome.player_name == "Patrick Mahomes"

    def test_market_offer_methods(self):
        over_odds = OddsValue.from_american(-110)
        under_odds = OddsValue.from_american(-110)

        offer = MarketOffer(
            market_key="player_pass_yds",
            label="Patrick Mahomes - Passing Yards",
            player_name="Patrick Mahomes",
            point=268.5,
            bookmaker="bet365",
            outcomes=[
                MarketOutcome(name="Over", point=268.5, odds=over_odds, outcome_type=OutcomeType.OVER),
                MarketOutcome(name="Under", point=268.5, odds=under_odds, outcome_type=OutcomeType.UNDER),
            ],
        )

        assert offer.is_two_way is True
        assert offer.get_outcome("over") is not None
        assert offer.get_outcome("under") is not None
        assert offer.get_outcome("away") is None
        # Implied prob each ~ 0.52381 -> sum ~ 1.0476
        assert offer.overround == pytest.approx(1.0476, rel=1e-3)

    def test_event_and_bookmaker_helpers(self):
        offer = MarketOffer(
            market_key="h2h",
            label="Moneyline",
            bookmaker="bet365",
            outcomes=[
                MarketOutcome(name="Kansas City Chiefs", odds=OddsValue.from_american(105), outcome_type=OutcomeType.AWAY),
                MarketOutcome(name="Buffalo Bills", odds=OddsValue.from_american(-125), outcome_type=OutcomeType.HOME),
            ],
        )
        book = Bookmaker(key="bet365", title="Bet365", markets=[offer])
        event = Event(
            id="test_event_1",
            commence_time=datetime(2026, 9, 13, 20, 25, tzinfo=timezone.utc),
            home_team="Buffalo Bills",
            away_team="Kansas City Chiefs",
            home_team_canonical="BUF",
            away_team_canonical="KC",
            bookmakers=[book],
        )

        assert event.game_title == "KC @ BUF"
        assert event.get_bookmaker("bet365") is not None
        assert event.get_bookmaker("pinnacle") is None
        assert book.get_market("h2h") is not None
        assert book.get_market("spreads") is None


class TestProjectionsAndEVModels:
    """Test suite for Projections and EV calculation schemas."""

    def test_stat_category_mappings(self):
        assert StatCategory.from_market_key("player_pass_yds") == StatCategory.PASSING_YARDS
        assert StatCategory.from_market_key("player_rush_yds") == StatCategory.RUSHING_YARDS
        assert StatCategory.from_market_key("player_anytime_td") == StatCategory.ANYTIME_TD
        assert StatCategory.from_market_key("unknown_key") is None

        assert StatCategory.from_fantasypoints_header("Pass Yds") == StatCategory.PASSING_YARDS
        assert StatCategory.from_fantasypoints_header("rush_yds") == StatCategory.RUSHING_YARDS
        assert StatCategory.from_fantasypoints_header("Rec") == StatCategory.RECEPTIONS
        assert StatCategory.from_fantasypoints_header("Int") == StatCategory.PASSING_INTERCEPTIONS

        assert StatCategory.PASSING_YARDS.to_market_key() == "player_pass_yds"
        assert StatCategory.PASSING_YARDS.is_continuous is True
        assert StatCategory.ANYTIME_TD.is_continuous is False

    def test_player_projection_model(self):
        proj = PlayerProjection(
            player_name="Patrick Mahomes II",
            canonical_name="Patrick Mahomes",
            team="KC",
            position="QB",
            stat_category=StatCategory.PASSING_YARDS,
            projection_mean=282.4,
            projection_floor=230.0,
            projection_ceiling=340.0,
        )
        assert proj.player_name == "Patrick Mahomes II"
        assert proj.canonical_name == "Patrick Mahomes"
        assert proj.projection_mean == 282.4

    def test_ev_result_and_matched_opportunity(self):
        ev_res = EVResult(
            market_implied_ev=0.045,
            model_implied_ev=0.062,
            blended_ev=0.052,
            blended_win_prob=0.551,
            prob_push=0.0,
            quarter_kelly_fraction=0.0136,
            quarter_kelly_stake=27.20,
            half_kelly_stake=54.40,
            full_kelly_stake=108.80,
            recommended_stake=27.20,
        )
        assert ev_res.blended_ev == 0.052
        assert ev_res.recommended_stake == 27.20

        opp = MatchedEVOpportunity(
            id="opp_hash_123",
            event_id="e9b28a8d110f4439a0fa0e1819bc5a11",
            game="KC @ BUF",
            commence_time=datetime(2026, 9, 13, 20, 25, tzinfo=timezone.utc),
            player_name="Patrick Mahomes",
            canonical_name="Patrick Mahomes",
            team="KC",
            position="QB",
            market_key="player_pass_yds",
            market_label="Passing Yards",
            stat_category=StatCategory.PASSING_YARDS,
            line=268.5,
            outcome_name="Over",
            outcome_type=OutcomeType.OVER,
            target_book="bet365",
            target_american=-110,
            target_decimal=1.909091,
            benchmark_book="pinnacle",
            benchmark_american=-122,
            benchmark_decimal=1.82,
            market_fair_prob=0.55,
            market_fair_decimal=1.818,
            model_fair_prob=0.56,
            model_fair_decimal=1.785,
            blended_win_prob=0.554,
            prob_push=0.0,
            market_ev=0.050,
            model_ev=0.069,
            blended_ev=0.058,
            edge_pct=5.80,
            quarter_kelly=0.015,
            half_kelly=0.030,
            full_kelly=0.060,
            quarter_kelly_stake=30.0,
            half_kelly_stake=60.0,
            full_kelly_stake=120.0,
            recommended_stake=30.0,
        )
        assert opp.id == "opp_hash_123"
        assert opp.edge_pct == 5.80
        assert opp.is_positive_ev is True
