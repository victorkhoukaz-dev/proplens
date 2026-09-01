"""Tests for Phase 1.1 projection snapshot lifecycle."""

import pytest
from fastapi.testclient import TestClient

from app.db.cache import cache
from app.db.loaded_data_store import loaded_data_store
from app.db.projection_snapshot_store import projection_snapshot_store
from app.main import app


@pytest.fixture
def isolated_snapshot_store(tmp_path, monkeypatch):
    monkeypatch.setattr(projection_snapshot_store, "path", tmp_path / "projection_snapshots.json")
    monkeypatch.setattr(loaded_data_store, "path", tmp_path / "loaded_data.json")
    cache.replace_projections([])
    yield
    cache.replace_projections([])


@pytest.fixture
def client(isolated_snapshot_store):
    return TestClient(app)


def projection_text(rushing_yards: float) -> str:
    return f"Player,Team,Pos,Opp,Rush Yds\nSaquon Barkley,PHI,RB,DAL,{rushing_yards}\n"


def test_pasted_projection_import_creates_active_week_snapshot(client):
    response = client.post(
        "/api/upload/paste",
        json={
            "data_type": "projections",
            "content": projection_text(70.5),
            "season": 2026,
            "week": 2,
            "label": "Friday update",
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["snapshot"]["active"] is True
    assert data["snapshot"]["season"] == 2026
    assert data["snapshot"]["week"] == 2
    assert data["snapshot"]["label"] == "Friday update"

    library = client.get("/api/projection-library").json()
    assert len(library["snapshots"]) == 1
    assert library["snapshots"][0]["matchup_count"] == 1

    players = client.get("/api/evaluator/players?q=saquon").json()
    assert players["projection_context"]["week"] == 2
    assert players["players"][0]["opponent"] == "DAL"
    assert players["players"][0]["projections"]["rushing_yards"] == 70.5


def test_active_snapshot_cannot_be_deleted_and_inactive_snapshot_can(client):
    first = client.post(
        "/api/upload/paste",
        json={"data_type": "projections", "content": projection_text(70.5), "season": 2026, "week": 1},
    ).json()["snapshot"]
    second = client.post(
        "/api/upload/paste",
        json={"data_type": "projections", "content": projection_text(65.5), "season": 2026, "week": 2},
    ).json()["snapshot"]

    active_delete = client.delete(f"/api/projection-library/{second['id']}")
    assert active_delete.status_code == 409

    deleted = client.delete(f"/api/projection-library/{first['id']}")
    assert deleted.status_code == 200

    library = client.get("/api/projection-library").json()
    assert [item["id"] for item in library["snapshots"]] == [second["id"]]
