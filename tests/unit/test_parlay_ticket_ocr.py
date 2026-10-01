"""Ticket OCR is a draft aid, never an authority to create a wager."""

from app.services.parlay_ticket_ocr import parse_parlay_ticket


def test_extracts_ticket_price_stake_bonus_and_structured_legs():
    draft = parse_parlay_ticket("""
    2-Leg Parlay
    Saquon Barkley Over 70.5 Rushing Yards
    Anytime Touchdown Scorer - Justin Jefferson
    Combined Odds 9.75
    Bonus Bet Stake $5.00
    Potential Return $43.75
    """)
    assert draft["combined_odds"] == 9.75
    assert draft["stake"] == 5
    assert draft["bet_type"] == "bonus"
    assert [leg["market"] for leg in draft["legs"]] == ["rushing_yards", "anytime_td"]
    assert [leg["player_name"] for leg in draft["legs"]] == ["Saquon Barkley", "Justin Jefferson"]
    assert all(leg["decimal_odds"] is None for leg in draft["legs"])
    assert draft["warnings"] == []


def test_ambiguous_ticket_does_not_guess_cash_or_missing_price():
    draft = parse_parlay_ticket("""
    3 Leg Parlay
    Over 4.5 Receptions
    Amon-Ra St. Brown
    Total Return $30.00
    """)
    assert draft["combined_odds"] is None
    assert draft["stake"] is None
    assert draft["bet_type"] is None
    assert draft["expected_leg_count"] == 3
    assert len(draft["legs"]) == 1
    assert any("only 1" in warning for warning in draft["warnings"])


def test_american_total_odds_convert_only_when_explicitly_labeled():
    draft = parse_parlay_ticket("""
    Price +850
    Wager Amount 2.00
    Cash Bet
    Travis Kelce Over 39.5 Receiving Yards
    """)
    assert draft["combined_odds"] == 9.5
    assert draft["bet_type"] == "cash"
    assert draft["stake"] == 2


def test_combined_odds_beat_unrelated_price_and_game_leg_stays_free_text():
    draft = parse_parlay_ticket("""
    2-Leg Parlay
    Odds Boost 25.00%
    Eagles Moneyline
    Justin Jefferson Anytime TD
    Combined Odds 8.50
    Stake $2.00
    """)
    assert draft["combined_odds"] == 8.5
    assert len(draft["legs"]) == 2
    assert draft["legs"][1] == {"entry_mode": "free_text", "description": "Eagles Moneyline"}
    assert any("free text" in warning for warning in draft["warnings"])


def test_unreadable_odds_do_not_fall_through_to_stake():
    draft = parse_parlay_ticket("Combined Odds 9.795\nStake $5.00\nBonus Bet")
    assert draft["combined_odds"] is None
    assert draft["stake"] == 5
    draft = parse_parlay_ticket("Combined Odds\nStake $5.00")
    assert draft["combined_odds"] is None
    assert parse_parlay_ticket("Combined Odds\n9.75")["combined_odds"] == 9.75


def test_bet365_share_ticket_plus_selections_and_two_column_wager():
    draft = parse_parlay_ticket("""Thu 01 Oct 10:00 bet365
f) Reuse Selections (t) Share
O Garrett Wilson: 90+ Rec Yards 2.65
Receiving Yds
NY Jets Sun Oct 4
CHI Bears 1:00 PM
O SAME GAME PARLAY 4.90
Josh Downs: 90+ Rec Yards
| Receiving Yds
Stefon Diggs: 4+ Receptions
Receptions
IND Colts Sun Oct 4
WAS Commanders 9:30 AM
Wager To Return
$6.00 $77.91""")
    assert [leg["player_name"] for leg in draft["legs"]] == ["Garrett Wilson", "Josh Downs", "Stefon Diggs"]
    assert [leg["line"] for leg in draft["legs"]] == [89.5, 89.5, 3.5]
    assert all(leg["side_label"] == "Over" for leg in draft["legs"])
    assert draft["stake"] == 6
    assert draft["combined_odds"] == 12.985  # 4.90 is only the SGP subgroup price.
    assert draft["bet_type"] == "cash"
    assert any("calculated" in warning for warning in draft["warnings"])


def test_bonus_payout_excludes_stake_and_explicit_odds_take_priority():
    for ticket in (
        "Wager To Return\n$6.00 Bonus Bet $77.91",
        "Wager Bonus Bet To Return\n$6.00 $77.91",
        "Wager\n$6.00 Bonus Bet\nTo Return\n$77.91",
    ):
        draft = parse_parlay_ticket(ticket)
        assert draft["stake"] == 6
        assert draft["bet_type"] == "bonus"
        assert draft["combined_odds"] == 13.985
    draft = parse_parlay_ticket("Combined Odds 14.00\nWager To Return\n$6.00 Bonus Bet $77.91")
    assert draft["combined_odds"] == 14
    assert not any("calculated" in warning for warning in draft["warnings"])


def test_payout_calculation_requires_valid_wager_and_return():
    for ticket in ("Wager To Return\n$0.00 $77.91", "Wager $6.00", "To Return $77.91", "Wager To Return\n$6.00 $0.00"):
        assert parse_parlay_ticket(ticket)["combined_odds"] is None


def test_single_sgp_bonus_ticket_with_net_return_and_game_total():
    draft = parse_parlay_ticket("""Thu 01 Oct 10:43 bet365
fy Reuse Selections (t) Share
O SAME GAME PARLAY 11.00
Terry McLaurin - Over 4.5 Receptions
Receptions O/U
Josh Downs: 70+ Rec Yards
Receiving Yds
Stefon Diggs: 40+ Rec Yards
Receiving Yds
Over 49.5 Points
Total
IND Colts Sun Oct 4
WAS Commanders 9:30 AM
Wager Net Return
$4.00 $40
$4.00 Bonus Bets +)""")
    assert draft["combined_odds"] == 11
    assert draft["stake"] == 4
    assert draft["bet_type"] == "bonus"
    assert len(draft["legs"]) == 4
    assert draft["legs"][3] == {"entry_mode": "free_text", "description": "Over 49.5 Points (game total)"}
    assert not any("not read" in warning for warning in draft["warnings"])


def test_net_return_calculation_and_sgp_subgroup_safeguard():
    draft = parse_parlay_ticket("Wager Net Return\n$4.00 $40\n$4.00 Bonus Bets")
    assert draft["combined_odds"] == 11
    draft = parse_parlay_ticket("Garrett Wilson: 90+ Rec Yards 2.65\nSAME GAME PARLAY 4.90\nJosh Downs: 70+ Rec Yards")
    assert draft["combined_odds"] is None


def test_extract_endpoint_returns_draft_without_saving_a_parlay(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from app.api import routes
    from app.db.parlay_tracker_store import parlay_tracker_store
    from app.main import app

    monkeypatch.setattr(parlay_tracker_store, "path", tmp_path / "tracked_parlays.json")
    monkeypatch.setattr(routes, "extract_screenshot", lambda content, filename: {
        "raw_text": "2-leg parlay\nSaquon Barkley Over 70.5 Rushing Yards\nJustin Jefferson Anytime TD\nCombined Odds 9.75\nStake $5.00",
    })
    response = TestClient(app).post(
        "/api/parlay-screenshots/extract",
        files={"file": ("ticket.png", b"image bytes", "image/png")},
    )
    assert response.status_code == 200
    assert len(response.json()["draft"]["legs"]) == 2
    assert parlay_tracker_store.list() == []
