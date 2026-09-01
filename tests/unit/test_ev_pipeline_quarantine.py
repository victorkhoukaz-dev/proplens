from datetime import datetime, timezone

from app.db.cache import AppSettings
from app.schemas.odds import Bookmaker, Event, MarketOffer, MarketOutcome, OddsValue, OutcomeType
from app.services.ev_pipeline import EVPipellineService, SUSPICIOUS_EV_THRESHOLD_PCT


def _spread_offer(bookmaker: str, home_decimal: float, away_decimal: float) -> MarketOffer:
    return MarketOffer(
        market_key="spreads",
        market_type="spreads",
        label="Handicap (incl. overtime)",
        point=-4.5,
        bookmaker=bookmaker,
        outcomes=[
            MarketOutcome(
                name="Home",
                point=-4.5,
                odds=OddsValue.from_decimal(home_decimal),
                outcome_type=OutcomeType.HOME,
            ),
            MarketOutcome(
                name="Away",
                point=-4.5,
                odds=OddsValue.from_decimal(away_decimal),
                outcome_type=OutcomeType.AWAY,
            ),
        ],
    )


def _event(target_home_decimal: float) -> Event:
    return Event(
        id=f"quarantine-{target_home_decimal}",
        commence_time=datetime(2026, 9, 10, tzinfo=timezone.utc),
        home_team="Seattle Seahawks",
        away_team="New England Patriots",
        home_team_canonical="SEA",
        away_team_canonical="NE",
        bookmakers=[
            Bookmaker(
                key="bet365",
                title="Bet365",
                markets=[_spread_offer("bet365", target_home_decimal, 1.267)],
            ),
            Bookmaker(
                key="pinnacle",
                title="Pinnacle",
                markets=[_spread_offer("pinnacle", 2.08, 1.806)],
            ),
        ],
    )


def test_suspicious_high_ev_is_visible_but_quarantined_with_zero_stake():
    opportunities = EVPipellineService.process_data(
        events=[_event(3.5)],
        projections=[],
        settings=AppSettings(bankroll=200.0, min_stake=1.0),
    )
    home = next(item for item in opportunities if item.outcome_type == OutcomeType.HOME)

    assert home.blended_ev >= SUSPICIOUS_EV_THRESHOLD_PCT
    assert home.is_quarantined is True
    assert home.recommended_stake == 0.0
    assert home.quarter_kelly_stake == 0.0
    assert home.half_kelly_stake == 0.0
    assert home.full_kelly_stake == 0.0
    assert home.quarantine_reason is not None
    assert "Verification Required" in home.tags


def test_edge_below_threshold_remains_actionable():
    opportunities = EVPipellineService.process_data(
        events=[_event(2.25)],
        projections=[],
        settings=AppSettings(bankroll=200.0, min_stake=1.0),
    )
    home = next(item for item in opportunities if item.outcome_type == OutcomeType.HOME)

    assert 0.0 < home.blended_ev < SUSPICIOUS_EV_THRESHOLD_PCT
    assert home.is_quarantined is False
    assert home.quarantine_reason is None
    assert home.recommended_stake > 0.0
