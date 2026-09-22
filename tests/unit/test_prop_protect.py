"""Prop Protect records confirmed bonus credits without allocating later wagers."""

import pytest

from app.db.bet_tracker_store import bet_tracker_store
from app.db.parlay_tracker_store import parlay_tracker_store
from app.services import prop_protect


@pytest.fixture
def stores(tmp_path, monkeypatch):
    monkeypatch.setattr(bet_tracker_store, "path", tmp_path / "bets.json")
    monkeypatch.setattr(parlay_tracker_store, "path", tmp_path / "parlays.json")


def test_confirmed_prop_protect_credit_has_no_bonus_wager_linkage(stores):
    source = bet_tracker_store.create({
        "player_name": "D. Moore",
        "stake": 25,
        "decimal_odds": 2,
        "bet_type": "cash",
        "status": "lost",
        "season": 2026,
        "week": 2,
    })
    bonus = bet_tracker_store.create({
        "player_name": "Bonus player",
        "stake": 2,
        "decimal_odds": 3,
        "bet_type": "bonus",
    })

    prop_protect.record_receipt("straight", source["id"], "injury_void", 25)
    report = prop_protect.overview()

    assert report == {"sources": [
        {
            "kind": "straight",
            "id": source["id"],
            "description": "D. Moore",
            "status": "lost",
            "season": 2026,
            "week": 2,
            "receipt": report["sources"][0]["receipt"],
        }
    ]}
    assert report["sources"][0]["receipt"]["amount"] == 25
    assert "links" not in report["sources"][0]
    assert "remaining" not in report["sources"][0]
    assert bonus["id"] in {bet["id"] for bet in bet_tracker_store.list()}
