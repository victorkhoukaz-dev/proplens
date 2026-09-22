"""Safety-net economics, actual cash accounting, and receipt lifecycle."""
import math

import pytest
from fastapi.testclient import TestClient

from app.db.bet_tracker_store import bet_tracker_store
from app.db.parlay_tracker_store import parlay_tracker_store
from app.main import app
from app.services.safety_net import estimate


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(parlay_tracker_store, "path", tmp_path / "parlays.json")
    monkeypatch.setattr(bet_tracker_store, "path", tmp_path / "bets.json")
    return TestClient(app)


def manual(**changes):
    return {"legs": ["Kelce receiving 20+", "Mahomes passing 200+"], "decimal_odds": 4,
            "stake": 5, "bet_type": "cash", "safety_net": {"refund_amount": 5, "conversion_rate": .6}, **changes}


def create(client, **changes):
    response = client.post("/api/tracker/parlays/manual", json=manual(**changes))
    assert response.status_code == 200, response.text
    return response.json()["parlay"]


def receipt(client, source, amount=5):
    return client.post(f"/api/tracker/safety-nets/{source['id']}/receipt", json={"amount": amount})


def summary(client):
    return client.get("/api/tracker/overall-summary").json()["summary"]


def test_five_dollar_example_and_cap():
    result = estimate(5, 20, 5, .6, .2)
    assert result["estimated_bonus_cash_value"] == 3
    assert result["ordinary_ev"] == -1
    assert result["expected_promo_value"] == 2.4
    assert result["adjusted_ev"] == 1.4
    assert result["break_even_probability"] == pytest.approx(2 / 17)
    assert estimate(10, 40, 5, .6)["break_even_probability"] == pytest.approx(7 / 37)
    assert estimate(5, 20, 5, 0)["break_even_probability"] == .25
    assert estimate(5, 20, 5, 1)["break_even_probability"] == 0
    assert estimate(5, 20, 5, .6)["adjusted_ev"] is None


@pytest.mark.parametrize("values", [(0, 20, 5, .6), (5, 20, 6, .6), (5, 20, 5, 1.1), (5, 20, 5, math.nan)])
def test_bad_estimates(values):
    with pytest.raises(ValueError):
        estimate(*values)


@pytest.mark.parametrize("bonus_status,profit,roi", [("lost", -5, -100), ("won", 5, 100)])
@pytest.mark.parametrize("kind", ["parlay", "straight"])
def test_cash_profit_never_uses_conversion(client, bonus_status, profit, roi, kind):
    source = create(client, status="lost")
    assert summary(client)["total_profit"] == -5
    assert receipt(client, source).status_code == 200
    assert summary(client)["total_profit"] == -5
    if kind == "parlay":
        bonus = create(client, bet_type="bonus", safety_net=None, decimal_odds=3)
    else:
        bonus = bet_tracker_store.create({"player_name": "Bonus player", "stake": 5, "decimal_odds": 3, "bet_type": "bonus"})
    assert summary(client)["total_profit"] == -5
    store = parlay_tracker_store if kind == "parlay" else bet_tracker_store
    store.settle(bonus["id"], bonus_status)
    totals = summary(client)
    assert totals["total_profit"] == profit
    assert totals["cash_wagered"] == 5
    assert totals["bonus_value_used"] == 5
    assert totals["total_roi_on_cash_risk_pct"] == roi
    report = client.get("/api/tracker/safety-nets").json()["sources"][0]
    assert report["receipt"]["amount"] == 5
    # Reload from disk, not a transient UI value.
    assert parlay_tracker_store.list()[-1]["safety_net_receipt"]["amount"] == 5


def test_win_does_not_issue_refund(client):
    source = create(client, status="won")
    assert receipt(client, source).status_code == 400
    assert summary(client)["total_profit"] == 15
    assert summary(client)["total_roi_on_cash_risk_pct"] == 300


@pytest.mark.parametrize("status", ["pending", "cancelled", "cashed_out", "push_adjusted", "void_adjusted"])
def test_other_outcomes_do_not_issue_refund(client, status):
    source = create(client, status=status, settlement_amount=3)
    assert receipt(client, source).status_code == 400


@pytest.mark.parametrize("changes", [
    {"bet_type": "bonus"}, {"safety_net": {"refund_amount": 6, "conversion_rate": .6}},
    {"safety_net": {"refund_amount": 5, "conversion_rate": 1.1}},
    {"safety_net": {"refund_amount": -5, "conversion_rate": .6}},
    {"safety_net": {"refund_amount": 5, "conversion_rate": "NaN"}},
    {"safety_net": {"refund_amount": 5.001, "conversion_rate": .6}},
])
def test_offer_validation(client, changes):
    assert client.post("/api/tracker/parlays/manual", json=manual(**changes)).status_code == 422
    assert parlay_tracker_store.list() == []


def test_receipt_corrections_do_not_depend_on_bonus_wager_links(client):
    source = create(client, status="lost")
    assert receipt(client, source, 6).status_code == 400
    assert receipt(client, source).status_code == 200
    assert receipt(client, source, 4).status_code == 200
    assert receipt(client, source, 5.01).status_code == 400
    assert client.post(f"/api/tracker/parlays/{source['id']}/settle", json={"status": "won"}).status_code == 400
    assert client.put(f"/api/tracker/parlays/{source['id']}/manual", json=manual(status="lost", safety_net=None)).status_code == 400
    assert receipt(client, source, None).status_code == 200
    assert client.post(f"/api/tracker/parlays/{source['id']}/settle", json={"status": "won"}).status_code == 200


def test_receipt_overview_has_no_bonus_wager_linkage(client):
    source = create(client, status="lost")
    receipt(client, source)
    report = client.get("/api/tracker/safety-nets").json()["sources"][0]
    assert report["receipt"]["amount"] == 5
    assert "links" not in report
    assert "remaining" not in report


def test_old_client_edit_preserves_offer_and_receipt(client):
    source = create(client, status="lost")
    receipt(client, source)
    body = manual(status="lost", description="Corrected description")
    del body["safety_net"]
    response = client.put(f"/api/tracker/parlays/{source['id']}/manual", json=body)
    assert response.status_code == 200
    assert response.json()["parlay"]["safety_net"]["conversion_rate"] == .6
    assert response.json()["parlay"]["safety_net_receipt"]["amount"] == 5


def test_overview_includes_receipt_context_for_tracker_kpi(client):
    source = create(client, status="lost", season=2026, week=3)
    assert receipt(client, source).status_code == 200
    report = client.get("/api/tracker/safety-nets").json()["sources"]
    assert report[0]["season"] == 2026
    assert report[0]["week"] == 3


def test_overview_derives_week_from_matching_parlay_leg_context(client):
    source = create(client, status="lost")
    saved = parlay_tracker_store.list()[0]
    legs = [
        {**leg, "result_identity": {"season": 2026, "week": 2}}
        for leg in saved["legs"]
    ]
    parlay_tracker_store.update(source["id"], {"season": None, "week": None, "legs": legs})
    assert receipt(client, source).status_code == 200
    report = client.get("/api/tracker/safety-nets").json()["sources"]
    assert report[0]["season"] == 2026
    assert report[0]["week"] == 2
