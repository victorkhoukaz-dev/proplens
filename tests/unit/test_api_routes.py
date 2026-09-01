"""
tests/unit/test_api_routes.py: Test suite for FastAPI routes and endpoints.
"""
import pytest
from pathlib import Path
from fastapi.testclient import TestClient
from app.main import app
from app.adapters.csv_odds_adapter import CSVOddsAdapter
from app.db.cache import cache
from app.db.loaded_data_store import loaded_data_store
from app.db.settings_store import settings_store

client = TestClient(app)


@pytest.fixture(autouse=True)
def isolate_saved_settings(tmp_path, monkeypatch):
    monkeypatch.setattr(settings_store, "path", tmp_path / "settings.json")
    monkeypatch.setattr(loaded_data_store, "path", tmp_path / "loaded_data.json")


def test_health_endpoint():
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_settings_endpoints():
    get_res = client.get("/api/settings")
    assert get_res.status_code == 200
    assert "bankroll" in get_res.json()

    post_res = client.post("/api/settings", json={"bankroll": 5000.0, "kelly_fraction": 0.50})
    assert post_res.status_code == 200
    assert post_res.json()["settings"]["bankroll"] == 5000.0
    assert post_res.json()["settings"]["kelly_fraction"] == 0.50


def test_live_routes_use_oddspapi_adapter(monkeypatch):
    sample_path = Path(__file__).resolve().parent.parent.parent / "sample_data" / "odds_snapshot_sample.json"
    events = CSVOddsAdapter().parse_payload(sample_path.read_text(encoding="utf-8"))
    calls = []

    class FakeOddsPapiAdapter:
        def __init__(self, **kwargs):
            calls.append(("init", kwargs))
            self.remaining_requests = 42
            self.used_requests = 2

        async def fetch_odds(self):
            calls.append(("fetch", None))
            return events

    monkeypatch.setattr("app.api.routes.OddsPapiAdapter", FakeOddsPapiAdapter)

    save_response = client.post("/api/settings", json={"odds_api_key": "official-test-key"})
    assert save_response.status_code == 200
    assert save_response.json()["live_fetch"]["events_fetched"] == len(events)

    fetch_response = client.post("/api/fetch-live-odds")
    assert fetch_response.status_code == 200
    assert fetch_response.json()["remaining_requests"] == 42
    assert len([call for call in calls if call[0] == "fetch"]) == 2


def test_settings_rejects_error_text_as_api_key():
    response = client.post(
        "/api/settings",
        json={"odds_api_key": "❌ Error: Live fetch failed: HTTP 400"},
    )
    assert response.status_code == 422
    assert "Paste only the OddsPapi API key" in response.text


def test_opportunities_and_stats():
    stats_res = client.get("/api/stats")
    assert stats_res.status_code == 200
    assert "total_opportunities" in stats_res.json()
    assert "quarantined_count" in stats_res.json()

    opps_res = client.get("/api/opportunities?min_ev=-100.0")
    assert opps_res.status_code == 200
    data = opps_res.json()
    assert "opportunities" in data
    assert "total" in data


def test_recalculate_endpoint():
    res = client.post("/api/recalculate")
    assert res.status_code == 200
    assert res.json()["success"] is True
