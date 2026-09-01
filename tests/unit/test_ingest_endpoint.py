"""
Unit tests for Browser / Bet365 direct ingestion endpoints (/api/ingest and /api/ingest/bet365).
"""
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.db.cache import cache


@pytest.fixture
def client():
    return TestClient(app)


def test_ingest_bet365_props_passing_yards(client):
    cache.store_events([])
    payload = {
        "bookmaker": "bet365",
        "sport": "americanfootball_nfl",
        "props": [
            {
                "player": "Patrick Mahomes",
                "team": "KC",
                "market": "player_pass_yds",
                "line": 268.5,
                "over_odds": -110,
                "under_odds": -110,
                "game": "KC @ BAL",
            },
            {
                "player": "Lamar Jackson",
                "team": "BAL",
                "market": "player_pass_yds",
                "line": 218.5,
                "over_odds": -115,
                "under_odds": -105,
                "game": "KC @ BAL",
            },
        ],
        "append": True,
    }

    response = client.post("/api/ingest/bet365", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["props_ingested"] == 2
    assert data["markets_created"] >= 2

    # Verify cache has events with bet365
    events = cache.get_events()
    assert len(events) > 0
    found_mahomes = False
    for ev in events:
        bm = ev.get_bookmaker("bet365")
        if bm:
            for m in bm.markets:
                if m.player_canonical and m.player_canonical.lower() == "patrick mahomes" and m.market_key == "player_pass_yds":
                    found_mahomes = True
                    assert m.point == 268.5
                    assert len(m.outcomes) == 2
    assert found_mahomes



def test_ingest_bet365_anytime_td(client):
    payload = {
        "bookmaker": "bet365",
        "sport": "americanfootball_nfl",
        "props": [
            {
                "player": "Travis Kelce",
                "team": "KC",
                "market": "player_anytime_td",
                "line": 0.5,
                "price": "+125",
                "game": "KC @ BAL",
            }
        ],
        "append": True,
    }

    response = client.post("/api/ingest/bet365", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["props_ingested"] == 1


def test_ingest_empty_payload_fails(client):
    payload = {
        "bookmaker": "bet365",
        "props": [],
    }
    response = client.post("/api/ingest/bet365", json=payload)
    assert response.status_code == 400
