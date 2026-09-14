"""Read-only Phase 5.0 projection-mean accuracy research."""
from __future__ import annotations

import csv
import io
import math
import urllib.error
import urllib.request
from collections import Counter, defaultdict
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from app.core.normalizer import PlayerNameNormalizer, TeamNormalizer
from app.db.projection_snapshot_store import ProjectionSnapshot, projection_snapshot_store
from app.db.result_cache_store import result_cache_store
from app.services.result_preview import ResultPreviewError, result_preview_service


NFLVERSE_SCHEDULE_URL = "https://github.com/nflverse/nfldata/releases/download/schedules/games.csv"
SUPPORTED_MEAN_MARKETS = {
    "passing_yards": "passing yards",
    "rushing_yards": "rushing yards",
    "rushing_attempts": "rushing attempts",
    "receiving_yards": "receiving yards",
    "receptions": "receptions",
}
EASTERN = ZoneInfo("America/Toronto")


class ModelResearchError(RuntimeError):
    """A schedule/stat source issue that must never affect the live evaluator."""


def _as_int(value: str | None) -> int | None:
    try:
        return int(float(value or ""))
    except ValueError:
        return None


def _kickoff(raw: dict[str, str]) -> datetime | None:
    day = (raw.get("gameday") or raw.get("game_date") or "").strip()
    time = (raw.get("gametime") or raw.get("game_time") or "").strip()
    if not day or not time:
        return None
    for pattern in ("%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(f"{day} {time}", pattern).replace(tzinfo=EASTERN)
        except ValueError:
            continue
    return None


class ModelResearchService:
    """Build a reproducible report from immutable imports and final nflverse data."""

    def _download_schedule(self) -> str:
        request = urllib.request.Request(NFLVERSE_SCHEDULE_URL, headers={"User-Agent": "PropLens-ModelResearch/1.0"})
        try:
            with urllib.request.urlopen(request, timeout=45) as response:
                return response.read().decode("utf-8-sig")
        except urllib.error.HTTPError as exc:
            raise ModelResearchError(f"nflverse schedule returned HTTP {exc.code}.") from exc
        except urllib.error.URLError as exc:
            raise ModelResearchError(f"Could not reach nflverse schedule: {exc.reason}") from exc

    def _schedule_content(self, *, refresh: bool) -> tuple[str, str, bool]:
        cached = result_cache_store.get_nflverse_schedule()
        if cached and not refresh:
            return cached["content"], cached["fetched_at"], True
        try:
            saved = result_cache_store.save_nflverse_schedule(self._download_schedule())
            return saved["content"], saved["fetched_at"], False
        except ModelResearchError:
            if cached:
                return cached["content"], cached["fetched_at"], True
            raise

    @staticmethod
    def _schedule_rows(content: str) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for raw in csv.DictReader(io.StringIO(content)):
            season, week = _as_int(raw.get("season")), _as_int(raw.get("week"))
            home = TeamNormalizer.canonical_team(raw.get("home_team") or "")
            away = TeamNormalizer.canonical_team(raw.get("away_team") or "")
            kickoff = _kickoff(raw)
            if season is None or week is None or not home or not away or kickoff is None:
                continue
            if (raw.get("game_type") or "REG").upper() != "REG":
                continue
            rows.append({"season": season, "week": week, "home": home, "away": away, "kickoff": kickoff})
        return rows

    @staticmethod
    def _snapshot_rows(snapshots: list[ProjectionSnapshot], season: int | None, through_week: int | None) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for snapshot in snapshots:
            if season is not None and snapshot.season != season:
                continue
            if through_week is not None and snapshot.week > through_week:
                continue
            for projection in snapshot.projections:
                market = projection.stat_category.value
                if market not in SUPPORTED_MEAN_MARKETS:
                    continue
                rows.append({
                    "snapshot": snapshot,
                    "season": snapshot.season,
                    "week": snapshot.week,
                    "player_name": projection.player_name,
                    "player_key": PlayerNameNormalizer.clean_name(projection.canonical_name or projection.player_name),
                    "team": TeamNormalizer.canonical_team(projection.team),
                    "opponent": TeamNormalizer.canonical_team(projection.opponent or ""),
                    "position": projection.position,
                    "market": market,
                    "projection_mean": float(projection.projection_mean),
                })
        return rows

    def report(self, *, season: int | None = None, through_week: int | None = None, refresh: bool = False) -> dict[str, Any]:
        snapshots = projection_snapshot_store.list()
        imported = self._snapshot_rows(snapshots, season, through_week)
        if not imported:
            return {
                "success": True,
                "scope": {"season": season, "through_week": through_week},
                "coverage": {"supported_imported_rows": 0, "selected_pre_kickoff_rows": 0, "matched_rows": 0, "excluded": {}},
                "markets": [], "largest_errors": [], "sources": [],
                "message": "No compatible imported projection rows are available for this scope yet.",
            }

        try:
            schedule_content, schedule_fetched_at, schedule_cached = self._schedule_content(refresh=refresh)
            schedules = self._schedule_rows(schedule_content)
        except ModelResearchError as exc:
            return {
                "success": True,
                "scope": {"season": season, "through_week": through_week},
                "coverage": {"supported_imported_rows": len(imported), "selected_pre_kickoff_rows": 0, "matched_rows": 0, "excluded": {"schedule_source_unavailable": len(imported)}},
                "markets": [], "largest_errors": [], "sources": [], "message": str(exc),
            }

        schedule_index: dict[tuple[int, int, frozenset[str]], list[dict[str, Any]]] = defaultdict(list)
        for game in schedules:
            schedule_index[(game["season"], game["week"], frozenset((game["home"], game["away"])))].append(game)

        excluded: Counter[str] = Counter()
        selected: dict[tuple[Any, ...], dict[str, Any]] = {}
        for row in imported:
            if not row["team"] or not row["opponent"] or not row["player_key"]:
                excluded["missing_projection_identity"] += 1
                continue
            games = schedule_index.get((row["season"], row["week"], frozenset((row["team"], row["opponent"]))), [])
            if len(games) != 1:
                excluded["schedule_unavailable_or_ambiguous"] += 1
                continue
            game = games[0]
            imported_at = row["snapshot"].imported_at
            if imported_at.tzinfo is None:
                imported_at = imported_at.replace(tzinfo=EASTERN)
            if imported_at > game["kickoff"]:
                excluded["imported_after_kickoff"] += 1
                continue
            row["kickoff"] = game["kickoff"]
            key = (row["season"], row["week"], row["team"], row["opponent"], row["player_key"], row["market"])
            existing = selected.get(key)
            if existing is None or row["snapshot"].imported_at > existing["snapshot"].imported_at:
                selected[key] = row

        stat_rows: list[dict[str, Any]] = []
        sources = [{"source": "nflverse schedule", "fetched_at": schedule_fetched_at, "used_cache": schedule_cached}]
        seasons = sorted({row["season"] for row in selected.values()})
        stat_errors: dict[int, str] = {}
        for stat_season in seasons:
            try:
                content, fetched_at, used_cache = result_preview_service._season_content(stat_season, refresh=refresh)
                stat_rows.extend(result_preview_service._rows(content))
                sources.append({"source": "nflverse player stats", "season": stat_season, "fetched_at": fetched_at, "used_cache": used_cache})
            except ResultPreviewError as exc:
                stat_errors[stat_season] = str(exc)

        stats_index: dict[tuple[Any, ...], list[dict[str, Any]]] = defaultdict(list)
        for row in stat_rows:
            stats_index[(row["season"], row["week"], row["team"], row["opponent"], row["player_key"])].append(row)

        matched: list[dict[str, Any]] = []
        for row in selected.values():
            if row["season"] in stat_errors:
                excluded["player_stats_unavailable"] += 1
                continue
            matches = stats_index.get((row["season"], row["week"], row["team"], row["opponent"], row["player_key"]), [])
            if len(matches) != 1:
                excluded["player_stat_missing_or_ambiguous"] += 1
                continue
            actual = matches[0]["stats"].get(row["market"])
            if actual is None:
                excluded["final_stat_unavailable"] += 1
                continue
            error = float(actual) - row["projection_mean"]
            matched.append({
                **{key: row[key] for key in ("season", "week", "player_name", "team", "opponent", "position", "market", "projection_mean", "kickoff")},
                "snapshot_id": row["snapshot"].id,
                "snapshot_label": row["snapshot"].label,
                "snapshot_imported_at": row["snapshot"].imported_at.isoformat(),
                "actual_stat": float(actual),
                "error": round(error, 4),
                "absolute_error": round(abs(error), 4),
            })

        market_rows: list[dict[str, Any]] = []
        for market in SUPPORTED_MEAN_MARKETS:
            records = [row for row in matched if row["market"] == market]
            if not records:
                continue
            errors = [row["error"] for row in records]
            market_rows.append({
                "market": market,
                "label": SUPPORTED_MEAN_MARKETS[market],
                "sample_size": len(records),
                "average_projection": round(sum(row["projection_mean"] for row in records) / len(records), 2),
                "average_actual": round(sum(row["actual_stat"] for row in records) / len(records), 2),
                "bias_actual_minus_projection": round(sum(errors) / len(errors), 2),
                "mae": round(sum(abs(error) for error in errors) / len(errors), 2),
                "rmse": round(math.sqrt(sum(error * error for error in errors) / len(errors)), 2),
            })
        largest_errors = sorted(matched, key=lambda row: row["absolute_error"], reverse=True)[:10]
        return {
            "success": True,
            "scope": {"season": season, "through_week": through_week},
            "coverage": {
                "supported_imported_rows": len(imported),
                "selected_pre_kickoff_rows": len(selected),
                "matched_rows": len(matched),
                "excluded": dict(sorted(excluded.items())),
            },
            "markets": market_rows,
            "largest_errors": largest_errors,
            "sources": sources,
            "message": "Descriptive only — this report does not change model coefficients or saved bet history.",
        }


model_research_service = ModelResearchService()
