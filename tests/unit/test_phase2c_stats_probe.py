"""Fixture-only tests for the read-only Phase 2C.0 provider probes."""
import json
from email.message import Message
from pathlib import Path

from scripts.phase2c_stats_probe import (
    parse_nflverse_csv,
    select_espn_event,
    select_api_sports_game,
    summarize_espn_boxscore,
    summarize_api_sports,
)


FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "phase2c"


def test_nflverse_probe_finds_identity_and_prop_result_fields():
    report = parse_nflverse_csv(
        (FIXTURES / "nflverse_week.csv").read_text(encoding="utf-8"),
        season=2025,
        week=1,
        player_names=["Saquon Barkley", "Jalen Hurts"],
    )

    assert report["schema"]["usable"] is True
    assert report["week_row_count"] == 3
    assert report["matched_player_count"] == 2
    barkley = next(player for player in report["players"] if player["player_name"] == "Saquon Barkley")
    assert barkley["game_id"] == "2025_01_DAL_PHI"
    assert barkley["rushing_yards"] == 60
    assert barkley["receiving_yards"] == 24
    assert barkley["receptions"] == 4


def test_nflverse_probe_does_not_treat_missing_player_as_zero_stats():
    report = parse_nflverse_csv(
        (FIXTURES / "nflverse_week.csv").read_text(encoding="utf-8"),
        season=2025,
        week=1,
        player_names=["Inactive Player"],
    )

    assert report["matched_player_count"] == 0
    assert report["players"] == []


def test_api_sports_probe_only_reports_discovered_schema_and_quota():
    payload = json.loads((FIXTURES / "api_sports_schema.json").read_text(encoding="utf-8"))
    headers = Message()
    headers["x-ratelimit-requests-remaining"] = "99"
    headers["x-ratelimit-requests-limit"] = "100"

    report = summarize_api_sports(payload, headers, "/games/statistics/players")

    assert report["reported_results"] == 1
    assert "rushing_yards" in report["relevant_response_keys"]
    assert "players" in report["relevant_response_keys"]
    assert report["quota"]["requests_remaining"] == "99"
    assert "response" not in report
    assert report["sample_response"][0]["game"]["id"] == 123


def test_api_sports_schedule_is_filtered_by_returned_week_and_teams():
    payload = {
        "errors": [],
        "results": 2,
        "response": [
            {
                "game": {"id": 101, "week": "Week 1", "status": {"short": "FT"}},
                "teams": {
                    "home": {"name": "Philadelphia Eagles"},
                    "away": {"name": "Dallas Cowboys"},
                },
            },
            {
                "game": {"id": 102, "week": "Week 2", "status": {"short": "FT"}},
                "teams": {
                    "home": {"name": "Kansas City Chiefs"},
                    "away": {"name": "Philadelphia Eagles"},
                },
            },
        ],
    }

    matches, week_games = select_api_sports_game(
        payload,
        week=1,
        team_terms=["Philadelphia", "Dallas"],
    )

    assert [game["game"]["id"] for game in matches] == [101]
    assert [game["id"] for game in week_games] == [101]


def test_espn_probe_identifies_event_and_prop_stat_groups():
    scoreboard = {
        "events": [
            {
                "id": "401671616",
                "name": "Green Bay Packers at Philadelphia Eagles",
                "date": "2024-09-07T00:15Z",
                "status": {"type": {"name": "STATUS_FINAL"}},
                "competitions": [
                    {
                        "competitors": [
                            {"team": {"displayName": "Philadelphia Eagles"}},
                            {"team": {"displayName": "Green Bay Packers"}},
                        ]
                    }
                ],
            }
        ]
    }
    matches, available = select_espn_event(
        scoreboard,
        team_terms=["Philadelphia", "Green"],
    )
    assert matches[0]["id"] == "401671616"
    assert available[0]["status"] == "STATUS_FINAL"

    report = summarize_espn_boxscore(
        {
            "boxscore": {
                "players": [
                    {
                        "team": {"displayName": "Philadelphia Eagles"},
                        "statistics": [
                            {
                                "name": "rushing",
                                "names": ["CAR", "YDS", "AVG", "TD"],
                                "athletes": [
                                    {
                                        "athlete": {"id": "1", "displayName": "Saquon Barkley"},
                                        "stats": ["24", "109", "4.5", "2"],
                                    }
                                ],
                            },
                            {
                                "name": "receiving",
                                "names": ["REC", "YDS", "AVG", "TD", "TGTS"],
                                "athletes": [],
                            },
                            {"name": "passing", "names": ["C/ATT", "YDS", "TD", "INT"], "athletes": []},
                        ],
                    }
                ]
            }
        }
    )
    assert report["all_supported_groups_present"] is True
    rushing = next(group for group in report["groups"] if group["group"] == "rushing")
    assert rushing["sample_players"][0]["player_name"] == "Saquon Barkley"
    assert rushing["sample_players"][0]["stats"]["YDS"] == "109"


def test_espn_probe_uses_labels_when_names_are_not_present():
    report = summarize_espn_boxscore(
        {
            "boxscore": {
                "players": [
                    {
                        "team": {"displayName": "Philadelphia Eagles"},
                        "statistics": [
                            {
                                "name": "receiving",
                                "labels": ["REC", "YDS", "TD"],
                                "athletes": [
                                    {
                                        "athlete": {"id": "1", "displayName": "Example Player"},
                                        "stats": ["4", "24", "0"],
                                    }
                                ],
                            }
                        ],
                    }
                ]
            }
        }
    )
    receiving = report["groups"][0]
    assert receiving["columns"] == ["REC", "YDS", "TD"]
    assert receiving["sample_players"][0]["stats"] == {"REC": "4", "YDS": "24", "TD": "0"}
