import pytest
from fastapi.testclient import TestClient

from app.db.manual_bonus_credit_store import ManualBonusCreditStore, manual_bonus_credit_store
from app.main import app


def test_manual_bonus_credit_persists_amount_and_week_context(tmp_path):
    store = ManualBonusCreditStore(tmp_path / "credits.json")
    credit = store.create(12.5, 2026, 2)
    saved = store.list()
    assert saved == [credit]
    assert saved[0]["amount"] == 12.5
    assert saved[0]["season"] == 2026
    assert saved[0]["week"] == 2


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(manual_bonus_credit_store, "path", tmp_path / "credits.json")
    return TestClient(app)


def test_manual_bonus_credit_api_returns_tracker_receipt_shape(client):
    created = client.post(
        "/api/tracker/manual-bonus-credits",
        json={"amount": 15, "season": 2026, "week": 3},
    )

    assert created.status_code == 200
    sources = client.get("/api/tracker/manual-bonus-credits").json()["sources"]
    assert sources[0]["receipt"]["amount"] == 15
    assert sources[0]["season"] == 2026
    assert sources[0]["week"] == 3


def test_manual_bonus_credit_api_rejects_partial_week_context(client):
    response = client.post(
        "/api/tracker/manual-bonus-credits",
        json={"amount": 15, "season": 2026},
    )

    assert response.status_code == 400
    assert "both season and week" in response.json()["detail"]
