"""Preview-only tracked-bet result checks using nflverse final player statistics."""
from __future__ import annotations

import csv
import io
import urllib.error
import urllib.request
from collections import defaultdict
from collections.abc import Iterable
from typing import Any

from app.core.normalizer import PlayerNameNormalizer, TeamNormalizer
from app.db.result_cache_store import result_cache_store


NFLVERSE_PLAYER_STATS_URL = (
    "https://github.com/nflverse/nflverse-data/releases/download/"
    "stats_player/stats_player_week_{season}.csv"
)
SUPPORTED_MARKETS = {
    "passing_yards": ("passing_yards", "passing yards"),
    "rushing_yards": ("rushing_yards", "rushing yards"),
    "receiving_yards": ("receiving_yards", "receiving yards"),
    "receptions": ("receptions", "receptions"),
}
TOUCHDOWN_STAT_FIELDS = ("rushing_tds", "receiving_tds")


class ResultPreviewError(RuntimeError):
    """A provider/cache problem that must not change any tracked bet."""


def _number(value: str | None) -> float | None:
    try:
        return float(value) if value not in (None, "") else None
    except ValueError:
        return None


def _identity_ready(bet: dict[str, Any]) -> dict[str, Any] | None:
    identity = bet.get("result_identity")
    if not isinstance(identity, dict) or identity.get("status") != "ready":
        return None
    season, week = identity.get("season"), identity.get("week")
    if not isinstance(season, int) or not isinstance(week, int):
        return None
    if not identity.get("player_key") or not identity.get("team") or not identity.get("opponent"):
        return None
    return identity


class ResultPreviewService:
    def _download_season(self, season: int) -> str:
        request = urllib.request.Request(
            NFLVERSE_PLAYER_STATS_URL.format(season=season),
            headers={"User-Agent": "PropLens-ResultPreview/1.0"},
        )
        try:
            with urllib.request.urlopen(request, timeout=45) as response:
                return response.read().decode("utf-8-sig")
        except urllib.error.HTTPError as exc:
            raise ResultPreviewError(f"nflverse returned HTTP {exc.code}.") from exc
        except urllib.error.URLError as exc:
            raise ResultPreviewError(f"Could not reach nflverse: {exc.reason}") from exc

    def _season_content(self, season: int, *, refresh: bool) -> tuple[str, str, bool]:
        cached = result_cache_store.get_nflverse_season(season)
        if not refresh and cached:
            return cached["content"], cached["fetched_at"], True
        try:
            record = result_cache_store.save_nflverse_season(season, self._download_season(season))
            return record["content"], record["fetched_at"], False
        except ResultPreviewError:
            if cached:
                return cached["content"], cached["fetched_at"], True
            raise

    @staticmethod
    def _rows(content: str) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for raw in csv.DictReader(io.StringIO(content)):
            season, week = _number(raw.get("season")), _number(raw.get("week"))
            if season is None or week is None:
                continue
            rows.append(
                {
                    "season": int(season),
                    "week": int(week),
                    "player_key": PlayerNameNormalizer.clean_name(raw.get("player_display_name") or raw.get("player_name") or ""),
                    "team": TeamNormalizer.canonical_team(raw.get("team") or ""),
                    "opponent": TeamNormalizer.canonical_team(raw.get("opponent_team") or ""),
                    "stats": {
                        **{key: _number(raw.get(key)) for key in SUPPORTED_MARKETS},
                        **{key: _number(raw.get(key)) for key in TOUCHDOWN_STAT_FIELDS},
                    },
                }
            )
        return rows

    @staticmethod
    def _proposal(bet: dict[str, Any], rows: Iterable[dict[str, Any]]) -> dict[str, Any]:
        identity = _identity_ready(bet)
        base = {"bet_id": bet["id"], "player_name": bet["player_name"], "market": bet["market"], "line": bet["line"]}
        if bet.get("entry_origin") == "manual":
            return {**base, "status": "manual_required", "message": "Manual tracking entry. Confirm the result with Bet365 and settle it manually."}
        if not identity:
            return {**base, "status": "missing_context", "message": "Legacy bet: no reliable week, team, and opponent context was saved."}
        if bet["market"] not in SUPPORTED_MARKETS and bet["market"] != "anytime_td":
            return {**base, "status": "unsupported_market", "message": "This market stays manual until its grading rules are tested."}
        week_rows = [row for row in rows if row["season"] == identity["season"] and row["week"] == identity["week"]]
        game_rows = [row for row in week_rows if {row["team"], row["opponent"]} == {identity["team"], identity["opponent"]}]
        if not game_rows:
            return {**base, "status": "game_not_final", "message": "No final nflverse stat line is available for this game yet."}
        matches = [row for row in game_rows if row["team"] == identity["team"] and row["opponent"] == identity["opponent"] and row["player_key"] == identity["player_key"]]
        if len(matches) != 1:
            return {**base, "status": "player_review", "message": "Game stats exist, but this player was not matched safely. Review manually; missing does not mean zero."}
        if bet["market"] == "anytime_td":
            # nflverse's weekly player table proves a conventional offensive TD, but it does
            # not by itself rule out every Bet365-relevant return/recovery scoring edge case.
            # Therefore it can safely suggest a win, never an automatic loss.
            offensive_tds = sum(float(matches[0]["stats"].get(field) or 0) for field in TOUCHDOWN_STAT_FIELDS)
            if offensive_tds > 0:
                return {
                    **base,
                    "status": "proposal",
                    "proposed_result": "won",
                    "actual_stat": offensive_tds,
                    "stat_label": "offensive rushing/receiving TDs",
                    "message": "Preview only — a rushing or receiving touchdown proves this Anytime TD selection won.",
                }
            return {**base, "status": "player_review", "message": "No rushing or receiving touchdown was found. Do not infer a loss: review Bet365 settlement for return or recovery touchdown exceptions."}
        stat_field, label = SUPPORTED_MARKETS[bet["market"]]
        actual = matches[0]["stats"].get(stat_field)
        if actual is None:
            return {**base, "status": "player_review", "message": "The matched player has no usable statistic for this market."}
        line = float(bet["line"])
        side = str(bet.get("side_label", "")).casefold()
        proposed = "push" if actual == line else ("won" if (actual > line if side == "over" else actual < line) else "lost")
        return {
            **base,
            "status": "proposal",
            "proposed_result": proposed,
            "actual_stat": actual,
            "stat_label": label,
            "message": "Preview only — confirm it against Bet365 before recording the result.",
        }

    def preview(self, bets: list[dict[str, Any]], *, refresh: bool = True) -> dict[str, Any]:
        pending = [bet for bet in bets if bet.get("status") == "pending"]
        seasons = sorted(
            {
                _identity_ready(bet)["season"]
                for bet in pending
                if _identity_ready(bet) and (bet.get("market") in SUPPORTED_MARKETS or bet.get("market") == "anytime_td")
            }
        )
        rows: list[dict[str, Any]] = []
        source_checks: list[dict[str, Any]] = []
        errors: dict[int, str] = {}
        for season in seasons:
            try:
                content, fetched_at, used_cache = self._season_content(season, refresh=refresh)
                rows.extend(self._rows(content))
                source_checks.append({"season": season, "source": "nflverse", "fetched_at": fetched_at, "used_cache": used_cache})
            except ResultPreviewError as exc:
                errors[season] = str(exc)
        proposals = []
        for bet in pending:
            identity = _identity_ready(bet)
            if identity and identity["season"] in errors:
                unavailable = "HTTP 404" in errors[identity["season"]]
                message = (
                    f"Final nflverse stats are not available for {identity['season']} Week {identity['week']} yet. This bet remains pending."
                    if unavailable
                    else "Could not reach nflverse right now. This bet remains pending; try checking again later."
                )
                proposals.append(
                    {
                        "bet_id": bet["id"],
                        "player_name": bet["player_name"],
                        "market": bet["market"],
                        "line": bet["line"],
                        "status": "stats_unavailable" if unavailable else "source_error",
                        "message": message,
                    }
                )
            else:
                proposals.append(self._proposal(bet, rows))
        return {"preview_only": True, "checked_pending": len(pending), "sources": source_checks, "proposals": proposals}


result_preview_service = ResultPreviewService()
