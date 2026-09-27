"""The IDP import keeps the active offense and deduplicates shared EDGE rows."""
import io

import pytest
from fastapi.testclient import TestClient

from app.adapters.fantasypoints_idp import parse_idp_files
from app.db.cache import cache
from app.db.loaded_data_store import loaded_data_store
from app.db.projection_snapshot_store import projection_snapshot_store
from app.main import app


def idp_csv(name: str, position: str, tackles: str, assists: str) -> bytes:
    return (
        ',,,,,Projection,IDP Defense,,,,,,,\n'
        'RANK,NAME,Position,Team,OPP,FPTS,TCK,AST,SACK,INT,PD,TFL,FF,FR\n'
        f'1,{name},{position},MIN,@TB,12,{tackles},{assists},0,0,0,0,0,0\n'
    ).encode()


def test_parser_deduplicates_consistent_rows_and_rejects_conflicts():
    files = [("edge.csv", idp_csv("Dallas Turner", "EDGE", "2.5", "1")),
             ("lb.csv", idp_csv("Dallas Turner", "EDGE", "2.5", "1"))]
    projections, duplicates = parse_idp_files(files, season=2026, week=4)
    assert len(projections) == 1
    assert duplicates == 1
    assert projections[0].projection_mean == 3.5
    assert projections[0].opponent == "TB"
    with pytest.raises(ValueError, match="conflicting duplicate"):
        parse_idp_files([files[0], ("lb.csv", idp_csv("Dallas Turner", "EDGE", "3", "1"))], season=2026, week=4)


def test_same_name_on_two_teams_remains_two_projection_rows():
    first = idp_csv("Alex Example", "LB", "4", "2")
    second = idp_csv("Alex Example", "LB", "3", "1").replace(b",MIN,", b",BUF,")
    projections, duplicates = parse_idp_files([("min.csv", first), ("buf.csv", second)], season=2026, week=4)
    assert duplicates == 0
    try:
        cache.replace_projections(projections)
        assert len(cache.get_projections()) == 2
    finally:
        cache.replace_projections([])


def test_defensive_upload_preserves_offense_and_activation(tmp_path, monkeypatch):
    monkeypatch.setattr(projection_snapshot_store, "path", tmp_path / "snapshots.json")
    monkeypatch.setattr(loaded_data_store, "path", tmp_path / "loaded.json")
    cache.replace_projections([])
    client = TestClient(app)
    try:
        offensive = client.post("/api/upload/paste", json={
            "data_type": "projections", "content": "Player,Team,Pos,Opp,Rush Yds\nSaquon Barkley,PHI,RB,DAL,70.5\n",
            "season": 2026, "week": 4,
        })
        assert offensive.status_code == 200
        offense_id = offensive.json()["snapshot"]["id"]
        defensive = client.post("/api/upload/defensive-projections", data={"season": "2026", "week": "4"}, files=[
            ("files", ("edge.csv", io.BytesIO(idp_csv("Dallas Turner", "EDGE", "2.5", "1")), "text/csv")),
            ("files", ("lb.csv", io.BytesIO(idp_csv("Dallas Turner", "EDGE", "2.5", "1")), "text/csv")),
            ("files", ("db.csv", io.BytesIO(idp_csv("Quentin Lake", "DB", "6", "2")), "text/csv")),
        ])
        assert defensive.status_code == 200, defensive.text
        assert defensive.json()["count"] == 2
        assert defensive.json()["duplicate_count"] == 1
        library = client.get("/api/projection-library").json()
        assert library["active_id"] == offense_id
        assert library["active_defensive_id"] == defensive.json()["snapshot"]["id"]
        assert sum(item["active"] for item in library["snapshots"]) == 2
        assert {p.stat_category.value for p in cache.get_projections()} >= {"rushing_yards", "tackles_assists"}
        assert client.get("/api/evaluator/players?q=saquon").json()["players"]
        assert defensive.json()["snapshot"]["positions"] == {"EDGE": 1, "DB": 1}
        newer = client.post("/api/upload/defensive-projections", data={"season": "2026", "week": "4"}, files=[
            ("files", ("db.csv", io.BytesIO(idp_csv("Quentin Lake", "DB", "7", "2")), "text/csv")),
        ])
        assert newer.status_code == 200
        assert len([p for p in cache.get_projections() if p.stat_category.value == "tackles_assists"]) == 1
        restored = client.post(f'/api/projection-library/{defensive.json()["snapshot"]["id"]}/activate')
        assert restored.status_code == 200
        library = client.get("/api/projection-library").json()
        assert library["active_id"] == offense_id
        assert library["active_defensive_id"] == defensive.json()["snapshot"]["id"]
        assert len([p for p in cache.get_projections() if p.stat_category.value == "tackles_assists"]) == 2
        assert client.get("/api/evaluator/players?q=quentin").json()["players"] == []
        defensive_search = client.get("/api/evaluator/players?q=quentin&include_projection_only=true").json()["players"]
        assert defensive_search[0]["player_name"] == "quentin lake"
        assert defensive_search[0]["projection_only"] is True
        assert defensive_search[0]["projections"]["tackles_assists"] == 8
        assert client.post("/api/evaluator/evaluate", json={
            "player_name": "Quentin Lake", "stat_category": "tackles_assists",
            "side": "over", "line": 7.5, "odds": 1.9,
        }).status_code == 400
    finally:
        cache.replace_projections([])
