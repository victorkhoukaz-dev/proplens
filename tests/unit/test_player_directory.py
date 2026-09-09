"""Phase 4E player-directory tests using an isolated local directory file."""

import pytest
from fastapi.testclient import TestClient

from app.db.player_directory_store import player_directory_store
from app.main import app


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(player_directory_store, "path", tmp_path / "player_directory.json")
    return TestClient(app)


def directory_csv() -> bytes:
    return b"Player,Team,Pos\nSaquon Barkley,PHI,RB\nJa'Marr Chase,CIN,WR\nPatrick Mahomes,KC,QB\n"


def test_player_directory_import_search_and_replace(client):
    imported = client.post(
        "/api/player-directory/import",
        files={"file": ("week-one-roster.csv", directory_csv(), "text/csv")},
    )
    assert imported.status_code == 200
    assert imported.json()["count"] == 3
    assert imported.json()["summary"]["positions"] == ["QB", "RB", "WR"]

    search = client.get("/api/player-directory/search?q=chase").json()["players"]
    assert search == [{"player_name": "Ja'Marr Chase", "canonical_name": "jamarr chase", "team": "CIN", "position": "WR"}]

    replacement = client.post(
        "/api/player-directory/import",
        files={"file": ("replacement.csv", b"Name,Team Abbreviation,Position\nCeeDee Lamb,DAL,WR\n", "text/csv")},
    )
    assert replacement.status_code == 200
    assert replacement.json()["count"] == 1
    assert client.get("/api/player-directory/search?q=saquon").json()["players"] == []
    assert client.get("/api/player-directory/search?q=lamb").json()["players"][0]["team"] == "DAL"


def test_player_directory_skips_leading_blank_spreadsheet_rows(client):
    # Spreadsheet exports can preserve one or more visibly blank rows before headers.
    csv_with_blank_first_row = b",,\nPlayer,Position,Team\nJahmyr Gibbs,RB,DET\nJosh Allen,QB,BUF\n"
    imported = client.post(
        "/api/player-directory/import",
        files={"file": ("player_database.csv", csv_with_blank_first_row, "text/csv")},
    )
    assert imported.status_code == 200
    assert imported.json()["count"] == 2
    gibbs = client.get("/api/player-directory/search?q=gibbs").json()["players"][0]
    assert gibbs["position"] == "RB"
    assert gibbs["team"] == "DET"


def test_player_directory_rejects_missing_required_columns_and_can_clear(client):
    missing = client.post(
        "/api/player-directory/import",
        files={"file": ("missing.csv", b"Player,Team\nSaquon Barkley,PHI\n", "text/csv")},
    )
    assert missing.status_code == 400
    assert "Player, Team, and Pos" in missing.json()["detail"]

    client.post(
        "/api/player-directory/import",
        files={"file": ("roster.csv", directory_csv(), "text/csv")},
    )
    cleared = client.delete("/api/player-directory")
    assert cleared.status_code == 200
    assert cleared.json()["summary"]["count"] == 0
