"""Preview-only participation evidence. Never inserts zeros into research metrics."""
from __future__ import annotations

import csv
import io
import json
import math
import urllib.request
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

from app.core.normalizer import PlayerNameNormalizer, TeamNormalizer
from app.services.research_receiving_recovery import BOXSCORES_PATH, ReviewedReceivingRecovery

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE_PATH = Path(__file__).with_name("research_participation_evidence.json")
SNAP_URL = "https://github.com/nflverse/nflverse-data/releases/download/snap_counts/snap_counts_{season}.csv"


def identity(row):
    return (int(row["season"]), int(row["week"]),
            TeamNormalizer.canonical_team(row.get("team") or ""),
            TeamNormalizer.canonical_team(row.get("opponent") or ""),
            PlayerNameNormalizer.clean_name(row.get("player_name") or row.get("player") or ""))


class ResearchParticipationService:
    def __init__(self, cache_dir=None, evidence_path=EVIDENCE_PATH, boxscores_path=BOXSCORES_PATH):
        self.cache_dir = Path(cache_dir) if cache_dir else ROOT / "data" / "research" / "participation_cache"
        self.evidence_path = Path(evidence_path)
        self.boxscores_path = Path(boxscores_path)

    def _snap_content(self, season, refresh=False):
        path = self.cache_dir / f"snap_counts_{season}.json"
        cached = None
        try:
            cached = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(cached.get("content"), str):
                cached = None
        except (OSError, ValueError, AttributeError):
            pass
        if cached and not refresh:
            return {**cached, "used_cache": True, "warning": ""}
        try:
            request = urllib.request.Request(SNAP_URL.format(season=season), headers={"User-Agent": "PropLens-ResearchParticipation/1.0"})
            with urllib.request.urlopen(request, timeout=15) as response:
                content = response.read().decode("utf-8-sig")
            fields = csv.DictReader(io.StringIO(content)).fieldnames or []
            if not {"season", "week", "game_type", "player", "team", "opponent", "offense_snaps"}.issubset(fields):
                raise ValueError("Snap-count source has unexpected columns.")
            record = {"content": content, "fetched_at": datetime.now(timezone.utc).isoformat(), "url": SNAP_URL.format(season=season)}
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            temporary = path.with_suffix(".tmp")
            temporary.write_text(json.dumps(record), encoding="utf-8")
            temporary.replace(path)
            return {**record, "used_cache": False, "warning": ""}
        except (OSError, ValueError) as exc:
            if cached:
                return {**cached, "used_cache": True, "warning": f"Refresh unavailable; using saved snap counts: {exc}"}
            raise ValueError(f"Participation source unavailable: {exc}") from exc

    def preview(self, records, refresh=False):
        try:
            evidence = json.loads(self.evidence_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            evidence = []
        verified = defaultdict(list)
        for item in evidence:
            verified[identity(item)].append(item)
        snaps = defaultdict(list)
        receiving = ReviewedReceivingRecovery(self.boxscores_path)
        sources, warnings = [], list(receiving.warnings)
        for season in sorted({row["season"] for row in records if row["stage"] == "selected"}):
            try:
                source = self._snap_content(season, refresh)
                sources.append({key: source[key] for key in ("url", "fetched_at", "used_cache")})
                if source["warning"]:
                    warnings.append(source["warning"])
                for item in csv.DictReader(io.StringIO(source["content"])):
                    if item.get("game_type") != "REG":
                        continue
                    try:
                        count = float(item["offense_snaps"])
                        if not math.isfinite(count) or count < 0 or not count.is_integer():
                            continue
                        snaps[identity(item)].append({"offensive_snaps": int(count), "source_url": source["url"], "fetched_at": source["fetched_at"]})
                    except (ValueError, KeyError):
                        continue
            except ValueError as exc:
                warnings.append(str(exc))
        enriched = []
        for row in records:
            result = {"status": "not_checked" if row["stage"] != "selected" else "unresolved", "detail": "Import exclusion; participation check applies only to selected rows.", "sources": []}
            if row["stage"] == "selected":
                result["detail"] = "No verified participation/final-stat evidence. Missing records are not zero."
                key = identity(row)
                matches, facts = snaps.get(key, []), verified.get(key, [])
                played = len(matches) == 1 and matches[0]["offensive_snaps"] > 0
                fact = facts[0] if len(facts) == 1 else None
                if played:
                    result.update(offensive_snaps=matches[0]["offensive_snaps"], sources=[matches[0]["source_url"]], detail="Played offensive snaps; final market stat is not yet verified.")
                elif len(matches) > 1:
                    result["detail"] = "Multiple participation records; identity remains unresolved."
                if fact:
                    result["sources"] += fact["sources"]
                    result["reviewed_at"] = fact["reviewed_at"]
                    result["in_game_injury"] = fact.get("in_game_injury", False)
                    if fact["classification"] == "inactive" and played:
                        result["detail"] = "Conflicting inactive and offensive-snap evidence; unresolved."
                    elif fact["classification"] == "inactive" and len(matches) <= 1:
                        result.update(status="verified_nonparticipant", detail="Verified official inactive list; not a played-game zero.")
                    elif played and row.get("game_completed") and row["reason"] == "no_player_stat_record" and row["market"] in fact.get("zero_markets", []):
                        result.update(status="verified_played_zero", actual_stat=0.0, detail="Verified participation and final zero for this market. Preview only; not included in main metrics.")
                    elif played and not row.get("game_completed"):
                        result["detail"] = "Participation found, but final game completion is not verified; unresolved."
                if (played and row.get('game_completed') and row['reason'] == 'no_player_stat_record'
                        and len(facts) <= 1 and not (fact and fact['classification'] == 'inactive')):
                    recovery = receiving.check(row)
                    if recovery and recovery['verified_zero']:
                        result.update(status='verified_played_zero', actual_stat=0.0,
                                      detail=recovery['detail'], method='reviewed_receiving_table',
                                      reviewed_at=recovery['reviewed_at'])
                        result['sources'] = list(dict.fromkeys(result['sources'] + [recovery['source_url']]))
                    elif recovery:
                        # A contradictory or ambiguous table must not be overridden by a zero flag.
                        result.update(status='unresolved', detail=recovery['detail'])
                        result.pop('actual_stat', None)
            enriched.append({**row, "participation_preview": result})
        selected = [row for row in enriched if row["stage"] == "selected"]
        counts = dict(Counter(row["participation_preview"]["status"] for row in selected))
        game_statuses = defaultdict(set)
        for row in selected:
            game_statuses[identity(row)].add(row["participation_preview"]["status"])
        game_counts = dict(Counter("verified_nonparticipant" if "verified_nonparticipant" in states else "verified_played_zero" if "verified_played_zero" in states else "unresolved" for states in game_statuses.values()))
        recovery_counts = dict(Counter(row['participation_preview'].get('method', 'individual_review') for row in selected if row['participation_preview']['status'] == 'verified_played_zero'))
        return {"records": enriched, "participation": {"row_counts": counts, "player_game_counts": game_counts, "zero_verification_methods": recovery_counts, "sources": sources, "warnings": warnings, "preview_only": True}}


research_participation_service = ResearchParticipationService()
