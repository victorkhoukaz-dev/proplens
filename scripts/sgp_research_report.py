"""Generate a local QB/WR descriptive report: python -m scripts.sgp_research_report.

Only provider caches and a new report directory are written. Betting records and
projection snapshots are never modified. No third-party dependencies are added.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import html
import io
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

from app.core.normalizer import TeamNormalizer
from app.db.projection_snapshot_store import projection_snapshot_store
from app.db.result_cache_store import result_cache_store
from app.services.model_research import model_research_service


def build_pairs(records, schedule_content, stats_content, season, week):
    """Pair exact matched players, retaining review flags and final-game checks."""
    final_games = set()
    for game in csv.DictReader(io.StringIO(schedule_content)):
        if (game.get("season"), game.get("week"), game.get("game_type")) != (str(season), str(week), "REG"):
            continue
        try:
            float(game["home_score"])
            float(game["away_score"])
        except (KeyError, ValueError, TypeError):
            continue
        final_games.add(frozenset(TeamNormalizer.canonical_team(game[k]) for k in ("home_team", "away_team")))

    passers = defaultdict(set)
    for row in csv.DictReader(io.StringIO(stats_content)):
        if (row.get("season"), row.get("week"), row.get("season_type")) != (str(season), str(week), "REG"):
            continue
        try:
            attempts = float(row.get("attempts") or 0)
        except ValueError:
            continue
        if row.get("position") == "QB" and attempts > 0:
            key = tuple(TeamNormalizer.canonical_team(row.get(k)) for k in ("team", "opponent_team"))
            passers[key].add(row.get("player_id") or row.get("player_display_name"))

    groups = defaultdict(list)
    excluded = Counter()
    for row in records:
        if row["season"] != season or row["week"] != week:
            continue
        if (row["position"], row["market"]) not in {("QB", "passing_yards"), ("WR", "receiving_yards")}:
            continue
        if frozenset((row["team"], row["opponent"])) not in final_games:
            excluded["matched_player_game_not_confirmed_final"] += 1
            continue
        groups[(row["team"], row["opponent"])].append(row)

    pairs = []
    for (team, opponent), players in sorted(groups.items()):
        for qb in players:
            if qb["position"] != "QB":
                continue
            for wr in players:
                if wr["position"] != "WR":
                    continue
                flags = []
                if qb["projection_mean"] <= 0 or wr["projection_mean"] <= 0:
                    flags.append("zero_projection")
                if len(passers[(team, opponent)]) > 1:
                    flags.append("multiple_QBs_attempted_passes")
                if not passers[(team, opponent)]:
                    flags.append("QB_participation_unverified")
                pairs.append({"season": season, "week": week, "team": team, "opponent": opponent,
                              "kickoff": qb["kickoff"], "qb": qb, "wr": wr, "flags": flags})
    return pairs, dict(excluded)


def render_report(payload):
    esc = lambda value: html.escape(str(value))
    rows = []
    for pair in payload["pairs"]:
        cells = [pair["team"] + " vs " + pair["opponent"]]
        for role in ("qb", "wr"):
            p = pair[role]
            cells.extend([p["player_name"], f'{p["projection_mean"]:.1f}', f'{p["actual_stat"]:.1f}', f'{p["error"]:+.1f}', p["snapshot_imported_at"]])
        cells.append(", ".join(pair["flags"]) or "—")
        rows.append("<tr>" + "".join(f"<td>{esc(c)}</td>" for c in cells) + "</tr>")
    headers = ["Team / opponent", "QB", "Projected pass yd", "Actual", "Difference", "QB import (UTC)",
               "WR", "Projected rec yd", "Actual", "Difference", "WR import (UTC)", "Review flags"]
    return """<!doctype html><html lang="en"><meta charset="utf-8"><title>QB–WR research</title>
<style>body{font:15px system-ui;margin:28px;background:#101722;color:#e5edf7}h1{font-size:26px}
table{border-collapse:collapse;width:100%;font-size:13px}td,th{padding:9px;border-bottom:1px solid #344155;text-align:left}
th{background:#1d2939;position:sticky;top:0}pre{white-space:pre-wrap}p{max-width:1000px;line-height:1.6}</style>
""" + f"<h1>QB–WR research — {payload['season']} Week {payload['week']}</h1>" + \
        f"<p>Generated {esc(payload['generated_at'])}. {len(payload['pairs'])} matched pairs across {payload['games']} games.</p>" + \
        "<p>Difference = actual minus projection. These are projection errors, not sportsbook Over/Under results. " \
        "Pairs sharing a QB or game are related observations. This first table estimates no correlation, fair odds, or betting edge. " \
        "Review flags remain visible; multiple passers do not by themselves prove injury or explain the result.</p>" + \
        "<details><summary>Coverage, exclusions and sources</summary><pre>" + esc(json.dumps({k:v for k,v in payload.items() if k != "pairs"}, indent=2, default=str)) + \
        "</pre></details><table><thead><tr>" + "".join(f"<th>{esc(h)}</th>" for h in headers) + \
        "</tr></thead><tbody>" + "".join(rows) + "</tbody></table></html>"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--season", type=int, required=True)
    parser.add_argument("--week", type=int, required=True)
    parser.add_argument("--refresh", action="store_true", help="Refresh public nflverse schedule and stats caches")
    args = parser.parse_args()
    report = model_research_service.report(season=args.season, through_week=args.week, refresh=args.refresh, include_records=True)
    schedule = result_cache_store.get_nflverse_schedule()
    stats = result_cache_store.get_nflverse_season(args.season)
    if not schedule or not stats:
        raise SystemExit("Required schedule/stats unavailable: " + json.dumps(report, default=str))
    pairs, excluded = build_pairs(report.get("records", []), schedule["content"], stats["content"], args.season, args.week)
    now = datetime.now(timezone.utc)
    payload = {"season": args.season, "week": args.week, "generated_at": now.isoformat(),
               "method": "Latest compatible import strictly before kickoff; exact normalized player/team/opponent; scored REG games only.",
               "games": len({frozenset((p['team'], p['opponent'])) for p in pairs}),
               "teams": len({p['team'] for p in pairs}),
               "pair_flags": dict(Counter(flag for p in pairs for flag in p["flags"])),
               "phase5_coverage_through_week": report["coverage"], "pairing_exclusions": excluded,
               "sources": report["sources"],
               "input_sha256": {"snapshots": hashlib.sha256(projection_snapshot_store.path.read_bytes()).hexdigest(),
                                "schedule": hashlib.sha256(schedule["content"].encode()).hexdigest(),
                                "stats": hashlib.sha256(stats["content"].encode()).hexdigest()},
               "pairs": pairs}
    output = Path(__file__).resolve().parents[1] / "data" / "research" / f"sgp_{args.season}_week{args.week}_{now.strftime('%Y%m%dT%H%M%S%fZ')}"
    output.mkdir(parents=True, exist_ok=False)
    (output / "report.json").write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    (output / "report.html").write_text(render_report(payload), encoding="utf-8")
    print(json.dumps({"output": str(output), "pairs": len(pairs), "games": payload["games"], "teams": payload["teams"], "flags": payload["pair_flags"], "coverage": report["coverage"]}))


if __name__ == "__main__":
    main()
