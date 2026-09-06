"""Read-only Phase 2C.0 probes for NFL player-result data sources.

This script deliberately has no imports from the tracker and cannot settle bets.
It prints a compact diagnostic report to stdout and does not persist API keys.
"""
from __future__ import annotations

import argparse
import csv
from datetime import datetime
import getpass
import io
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Iterable
from typing import Any


NFLVERSE_PLAYER_STATS_URL = (
    "https://github.com/nflverse/nflverse-data/releases/download/"
    "stats_player/stats_player_week_{season}.csv"
)
API_SPORTS_BASE_URL = "https://v1.american-football.api-sports.io"
ESPN_NFL_BASE_URL = "https://site.api.espn.com/apis/site/v2/sports/football/nfl"
ESPN_PUBLIC_HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-CA,en;q=0.9",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0 Safari/537.36"
    ),
}

RESULT_FIELDS = (
    "passing_yards",
    "passing_tds",
    "passing_interceptions",
    "rushing_yards",
    "rushing_tds",
    "receptions",
    "receiving_yards",
    "receiving_tds",
)
IDENTITY_FIELDS = (
    "player_id",
    "player_display_name",
    "season",
    "week",
    "game_id",
    "team",
    "opponent_team",
)


class ProbeError(RuntimeError):
    """A safe, user-facing feasibility-probe failure."""


def _number(value: str | None) -> int | float | None:
    if value is None or value.strip() == "":
        return None
    try:
        number = float(value)
    except ValueError:
        return None
    return int(number) if number.is_integer() else number


def parse_nflverse_csv(
    content: str,
    *,
    season: int,
    week: int,
    player_names: Iterable[str] = (),
) -> dict[str, Any]:
    reader = csv.DictReader(io.StringIO(content))
    columns = reader.fieldnames or []
    missing_identity = [field for field in IDENTITY_FIELDS if field not in columns]
    missing_results = [field for field in RESULT_FIELDS if field not in columns]
    wanted_names = {name.casefold().strip() for name in player_names if name.strip()}
    matches: list[dict[str, Any]] = []
    week_rows = 0

    for row in reader:
        if _number(row.get("season")) != season or _number(row.get("week")) != week:
            continue
        week_rows += 1
        display_name = (row.get("player_display_name") or row.get("player_name") or "").strip()
        if wanted_names and display_name.casefold() not in wanted_names:
            continue
        matches.append(
            {
                "player_id": row.get("player_id"),
                "player_name": display_name,
                "game_id": row.get("game_id"),
                "team": row.get("team"),
                "opponent": row.get("opponent_team"),
                **{field: _number(row.get(field)) for field in RESULT_FIELDS},
            }
        )

    return {
        "source": "nflverse",
        "season": season,
        "week": week,
        "schema": {
            "column_count": len(columns),
            "missing_identity_fields": missing_identity,
            "missing_result_fields": missing_results,
            "usable": not missing_identity and not missing_results,
        },
        "week_row_count": week_rows,
        "requested_players": sorted(wanted_names),
        "matched_player_count": len(matches),
        "players": matches,
    }


def _request_bytes(url: str, *, headers: dict[str, str] | None = None) -> tuple[bytes, Any]:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "PropLens-Phase2C-Feasibility/1.0", **(headers or {})},
    )
    try:
        with urllib.request.urlopen(request, timeout=45) as response:
            return response.read(), response.headers
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")[:500]
        raise ProbeError(f"HTTP {exc.code} from data provider: {body}") from exc
    except urllib.error.URLError as exc:
        raise ProbeError(f"Could not reach data provider: {exc.reason}") from exc


def probe_nflverse(season: int, week: int, player_names: Iterable[str]) -> dict[str, Any]:
    url = NFLVERSE_PLAYER_STATS_URL.format(season=season)
    content, _ = _request_bytes(url)
    report = parse_nflverse_csv(
        content.decode("utf-8-sig"),
        season=season,
        week=week,
        player_names=player_names,
    )
    report["url"] = url
    report["download_bytes"] = len(content)
    return report


def _collect_keys(value: Any, output: set[str]) -> None:
    if isinstance(value, dict):
        for key, nested in value.items():
            output.add(str(key))
            _collect_keys(nested, output)
    elif isinstance(value, list):
        for nested in value[:25]:
            _collect_keys(nested, output)


def _compact_sample(value: Any, *, depth: int = 0) -> Any:
    """Keep enough response structure for feasibility review without dumping a full game."""
    if depth >= 6:
        return "..."
    if isinstance(value, dict):
        return {str(key): _compact_sample(nested, depth=depth + 1) for key, nested in value.items()}
    if isinstance(value, list):
        return [_compact_sample(nested, depth=depth + 1) for nested in value[:3]]
    return value


def summarize_api_sports(payload: dict[str, Any], headers: Any, endpoint: str) -> dict[str, Any]:
    keys: set[str] = set()
    _collect_keys(payload.get("response", []), keys)
    relevant_terms = ("yard", "reception", "touchdown", "interception", "player", "game", "team")
    return {
        "source": "api-sports",
        "endpoint": endpoint,
        "provider_errors": payload.get("errors"),
        "reported_results": payload.get("results"),
        "response_items": len(payload.get("response", [])) if isinstance(payload.get("response"), list) else None,
        "paging": payload.get("paging"),
        "relevant_response_keys": sorted(
            key for key in keys if any(term in key.casefold() for term in relevant_terms)
        ),
        "quota": {
            "requests_remaining": headers.get("x-ratelimit-requests-remaining"),
            "requests_limit": headers.get("x-ratelimit-requests-limit"),
        },
        "sample_response": _compact_sample(payload.get("response", [])[:1])
        if isinstance(payload.get("response"), list)
        else None,
        "note": "Schema discovery only; no tracker records were read or changed.",
    }


def select_api_sports_game(
    games_payload: dict[str, Any],
    *,
    week: int,
    team_terms: Iterable[str],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Filter a season schedule locally because API-NFL returns week as response data."""
    games = games_payload.get("response", [])
    if not isinstance(games, list):
        games = []
    terms = [term.casefold().strip() for term in team_terms if term.strip()]
    expected_week = f"week {week}"
    week_games = [
        game
        for game in games
        if str(game.get("game", {}).get("week", "")).casefold().strip() == expected_week
    ]
    candidates = [
        game
        for game in week_games
        if all(term in json.dumps(game.get("teams", {}), ensure_ascii=False).casefold() for term in terms)
    ]
    available_games = [
        {
            "id": game.get("game", {}).get("id"),
            "week": game.get("game", {}).get("week"),
            "teams": game.get("teams"),
            "status": game.get("game", {}).get("status"),
        }
        for game in week_games[:20]
    ]
    return candidates, available_games


def probe_api_sports(
    *,
    api_key: str,
    season: int,
    week: int,
    league: int,
    game_id: int | None,
) -> dict[str, Any]:
    if not api_key.strip():
        raise ProbeError(
            "API-Sports live test needs a free API key in the API_SPORTS_KEY environment variable."
        )
    if game_id is None:
        endpoint = "/games"
        params = {"league": league, "season": season, "week": week}
    else:
        endpoint = "/games/statistics/players"
        params = {"id": game_id}
    url = f"{API_SPORTS_BASE_URL}{endpoint}?{urllib.parse.urlencode(params)}"
    content, headers = _request_bytes(url, headers={"x-apisports-key": api_key.strip()})
    try:
        payload = json.loads(content)
    except json.JSONDecodeError as exc:
        raise ProbeError("API-Sports returned a response that was not valid JSON.") from exc
    return summarize_api_sports(payload, headers, endpoint)


def probe_api_sports_match(
    *,
    api_key: str,
    season: int,
    week: int,
    league: int,
    team_terms: Iterable[str],
) -> dict[str, Any]:
    """Use one schedule request and one stats request for a uniquely matched game."""
    if not api_key.strip():
        raise ProbeError(
            "API-Sports live test needs a free API key in the API_SPORTS_KEY environment variable."
        )
    terms = [term.casefold().strip() for term in team_terms if term.strip()]
    if len(terms) < 2:
        raise ProbeError("Provide two --team values to identify one historical game safely.")

    # API-NFL documents league + season for a schedule. Week is returned as
    # text (for example, "Week 1"), so filter it locally instead of sending
    # the unsupported numeric week parameter.
    games_url = f"{API_SPORTS_BASE_URL}/games?{urllib.parse.urlencode({'league': league, 'season': season})}"
    games_content, games_headers = _request_bytes(games_url, headers={"x-apisports-key": api_key.strip()})
    try:
        games_payload = json.loads(games_content)
    except json.JSONDecodeError as exc:
        raise ProbeError("API-Sports returned a schedule response that was not valid JSON.") from exc
    candidates, available_games = select_api_sports_game(
        games_payload,
        week=week,
        team_terms=terms,
    )
    if len(candidates) != 1:
        diagnostic = {
            "provider_errors": games_payload.get("errors"),
            "reported_results": games_payload.get("results"),
            "paging": games_payload.get("paging"),
            "quota": {
                "requests_remaining": games_headers.get("x-ratelimit-requests-remaining"),
                "requests_limit": games_headers.get("x-ratelimit-requests-limit"),
            },
            "week_games": available_games,
        }
        raise ProbeError(
            f"Expected one game matching {terms}, found {len(candidates)}. "
            f"Schedule diagnostic: {json.dumps(diagnostic, ensure_ascii=False)}"
        )

    selected = candidates[0]
    game_id = selected.get("game", {}).get("id")
    if game_id is None:
        raise ProbeError("The matched API-Sports game did not contain a game ID.")
    stats_url = f"{API_SPORTS_BASE_URL}/games/statistics/players?{urllib.parse.urlencode({'id': game_id})}"
    stats_content, stats_headers = _request_bytes(stats_url, headers={"x-apisports-key": api_key.strip()})
    stats_payload = json.loads(stats_content)
    return {
        "source": "api-sports",
        "requests_made": 2,
        "selected_game": _compact_sample(selected),
        "games_probe": summarize_api_sports(games_payload, games_headers, "/games"),
        "player_stats_probe": summarize_api_sports(
            stats_payload, stats_headers, "/games/statistics/players"
        ),
    }


def select_espn_event(
    scoreboard_payload: dict[str, Any], *, team_terms: Iterable[str]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Find one ESPN scoreboard event by two team-name fragments."""
    terms = [term.casefold().strip() for term in team_terms if term.strip()]
    events = scoreboard_payload.get("events", [])
    if not isinstance(events, list):
        events = []
    candidates = [
        event
        for event in events
        if all(term in json.dumps(event.get("competitions", []), ensure_ascii=False).casefold() for term in terms)
    ]
    available = [
        {
            "id": event.get("id"),
            "name": event.get("name"),
            "date": event.get("date"),
            "status": event.get("status", {}).get("type", {}).get("name"),
        }
        for event in events[:20]
    ]
    return candidates, available


def summarize_espn_boxscore(summary_payload: dict[str, Any]) -> dict[str, Any]:
    """Expose only player-stat schema and small samples for feasibility review."""
    boxscore = summary_payload.get("boxscore", {})
    team_blocks = boxscore.get("players", []) if isinstance(boxscore, dict) else []
    if not isinstance(team_blocks, list):
        team_blocks = []

    groups: list[dict[str, Any]] = []
    for team_block in team_blocks:
        team = team_block.get("team", {}) if isinstance(team_block, dict) else {}
        statistics = team_block.get("statistics", []) if isinstance(team_block, dict) else []
        if not isinstance(statistics, list):
            continue
        for statistic in statistics:
            if not isinstance(statistic, dict):
                continue
            name = str(statistic.get("name", "")).casefold()
            if name not in {"passing", "rushing", "receiving"}:
                continue
            columns = (
                statistic.get("names")
                or statistic.get("labels")
                or statistic.get("displayNames")
                or []
            )
            athletes = statistic.get("athletes", [])
            if not isinstance(columns, list):
                columns = []
            if not isinstance(athletes, list):
                athletes = []
            sample_players = []
            for athlete_row in athletes[:2]:
                if not isinstance(athlete_row, dict):
                    continue
                athlete = athlete_row.get("athlete", {})
                values = athlete_row.get("stats") or athlete_row.get("statistics") or []
                if not isinstance(values, list):
                    values = []
                sample_players.append(
                    {
                        "player_id": athlete.get("id") if isinstance(athlete, dict) else None,
                        "player_name": athlete.get("displayName") if isinstance(athlete, dict) else None,
                        "stats": dict(zip((str(column) for column in columns), values, strict=False)),
                    }
                )
            groups.append(
                {
                    "team": team.get("displayName") or team.get("name"),
                    "group": name,
                    "columns": columns,
                    "statistic_keys": sorted(statistic.keys()),
                    "player_count": len(athletes),
                    "sample_players": sample_players,
                }
            )

    present_groups = {group["group"] for group in groups}
    return {
        "team_blocks": len(team_blocks),
        "supported_groups_present": sorted(present_groups),
        "all_supported_groups_present": {"passing", "rushing", "receiving"}.issubset(present_groups),
        "groups": groups,
    }


def probe_espn_match(*, date: str, team_terms: Iterable[str]) -> dict[str, Any]:
    """Probe public ESPN scoreboard and box-score endpoints without credentials."""
    try:
        datetime.strptime(date, "%Y%m%d")
    except ValueError as exc:
        raise ProbeError("ESPN probe date must use YYYYMMDD, for example 20240906.") from exc
    terms = [term.casefold().strip() for term in team_terms if term.strip()]
    if len(terms) < 2:
        raise ProbeError("Provide two --team values to identify one ESPN game safely.")

    scoreboard_url = f"{ESPN_NFL_BASE_URL}/scoreboard?{urllib.parse.urlencode({'dates': date})}"
    scoreboard_content, _ = _request_bytes(scoreboard_url, headers=ESPN_PUBLIC_HEADERS)
    try:
        scoreboard_payload = json.loads(scoreboard_content)
    except json.JSONDecodeError as exc:
        raise ProbeError("ESPN returned a scoreboard response that was not valid JSON.") from exc
    candidates, available = select_espn_event(scoreboard_payload, team_terms=terms)
    if len(candidates) != 1:
        raise ProbeError(
            f"Expected one ESPN game matching {terms}, found {len(candidates)}. "
            f"Available game summary: {json.dumps(available, ensure_ascii=False)}"
        )

    selected = candidates[0]
    event_id = selected.get("id")
    if not event_id:
        raise ProbeError("The matched ESPN event did not contain an event ID.")
    summary_url = f"{ESPN_NFL_BASE_URL}/summary?{urllib.parse.urlencode({'event': event_id})}"
    summary_content, _ = _request_bytes(summary_url, headers=ESPN_PUBLIC_HEADERS)
    try:
        summary_payload = json.loads(summary_content)
    except json.JSONDecodeError as exc:
        raise ProbeError("ESPN returned a game-summary response that was not valid JSON.") from exc
    return {
        "source": "espn-public-endpoints",
        "requests_made": 2,
        "credential_required": False,
        "support_status": "Unofficial public endpoint; no stability or service guarantee.",
        "selected_game": {
            "event_id": event_id,
            "name": selected.get("name"),
            "date": selected.get("date"),
            "status": selected.get("status", {}).get("type", {}).get("name"),
        },
        "player_boxscore": summarize_espn_boxscore(summary_payload),
        "note": "Schema discovery only; no tracker records were read or changed.",
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run a read-only Phase 2C result-source probe.")
    subparsers = parser.add_subparsers(dest="provider", required=True)

    nflverse = subparsers.add_parser("nflverse", help="Probe the free nflverse weekly player-stat file.")
    nflverse.add_argument("--season", type=int, required=True)
    nflverse.add_argument("--week", type=int, required=True)
    nflverse.add_argument("--player", action="append", default=[], help="Exact display name; repeat as needed.")

    api_sports = subparsers.add_parser("api-sports", help="Probe API-Sports using API_SPORTS_KEY.")
    api_sports.add_argument("--season", type=int, required=True)
    api_sports.add_argument("--week", type=int, required=True)
    api_sports.add_argument("--league", type=int, default=1)
    api_sports.add_argument("--game-id", type=int)
    api_sports.add_argument(
        "--prompt-key",
        action="store_true",
        help="Prompt securely for the API key instead of reading API_SPORTS_KEY.",
    )
    api_sports.add_argument(
        "--team",
        action="append",
        default=[],
        help="Team-name fragment; provide twice to fetch one game's stats in two requests.",
    )

    espn = subparsers.add_parser("espn", help="Probe ESPN public scoreboard and box-score endpoints.")
    espn.add_argument("--date", required=True, help="Game date in YYYYMMDD format, for example 20240906.")
    espn.add_argument(
        "--team",
        action="append",
        default=[],
        help="Team-name fragment; provide twice to identify one game's box score.",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        if args.provider == "nflverse":
            report = probe_nflverse(args.season, args.week, args.player)
        elif args.provider == "api-sports":
            api_key = (
                getpass.getpass("Paste API-Sports key (input is hidden): ")
                if args.prompt_key
                else os.getenv("API_SPORTS_KEY", "")
            )
            if args.team:
                report = probe_api_sports_match(
                    api_key=api_key,
                    season=args.season,
                    week=args.week,
                    league=args.league,
                    team_terms=args.team,
                )
            else:
                report = probe_api_sports(
                    api_key=api_key,
                    season=args.season,
                    week=args.week,
                    league=args.league,
                    game_id=args.game_id,
                )
        else:
            report = probe_espn_match(date=args.date, team_terms=args.team)
    except ProbeError as exc:
        print(json.dumps({"success": False, "error": str(exc)}, indent=2))
        return 1
    print(json.dumps({"success": True, "report": report}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
