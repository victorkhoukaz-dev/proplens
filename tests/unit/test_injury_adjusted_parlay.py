"""Injury-adjusted bonus settlements remain linked to the original parlay."""

import pytest

from app.db.parlay_tracker_store import parlay_tracker_store
from app.services import injury_adjusted_parlay


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.setattr(parlay_tracker_store, "path", tmp_path / "parlays.json")


def test_bonus_parlay_injury_adjustment_has_zero_cash_profit_and_linked_credit(store):
    parlay = parlay_tracker_store.create({
        "description": "Bonus 3-leg parlay",
        "legs": [{"description": "Injured player"}, {"description": "Remaining winner"}],
        "stake": 5,
        "bet_type": "bonus",
        "winning_total_return": 20,
        "winning_return_includes_stake": False,
        "season": 2026,
        "week": 2,
    })

    saved = injury_adjusted_parlay.record_receipt(parlay["id"], 12.50, 0)

    assert saved["status"] == "lost"
    assert saved["profit"] == 0
    assert saved["injury_adjusted_parlay_settlement"] == {
        "amount": 12.50,
        "injured_leg_index": 0,
        "injured_leg_description": "Injured player",
        "remaining_legs_treated_as_won": True,
        "confirmed_at": saved["injury_adjusted_parlay_settlement"]["confirmed_at"],
    }
    report = injury_adjusted_parlay.overview()["sources"]
    assert report[0]["bet_type"] == "bonus"
    assert report[0]["receipt"]["amount"] == 12.50


def test_injury_adjustment_cannot_be_recorded_twice(store):
    parlay = parlay_tracker_store.create({
        "description": "Cash 2-leg parlay",
        "legs": [{"description": "Injured player"}, {"description": "Remaining winner"}],
        "stake": 5,
        "bet_type": "cash",
        "winning_total_return": 20,
        "winning_return_includes_stake": True,
        "season": 2026,
        "week": 2,
    })

    injury_adjusted_parlay.record_receipt(parlay["id"], 12.50, 0)

    with pytest.raises(ValueError, match="already has an injury-adjusted"):
        injury_adjusted_parlay.record_receipt(parlay["id"], 12.50, 0)
