"""Versioned local storage for imported projection sets."""
from __future__ import annotations

import json
import threading
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from pydantic import ValidationError

from app.schemas.projections import PlayerProjection


BASE_DIR = Path(__file__).resolve().parent.parent.parent
DEFAULT_SNAPSHOT_PATH = BASE_DIR / "data" / "projection_snapshots.json"


class ProjectionSnapshotNotFoundError(KeyError):
    pass


@dataclass(frozen=True)
class ProjectionSnapshot:
    id: str
    label: str
    source: str
    season: int
    week: int
    imported_at: datetime
    projections: list[PlayerProjection]

    def summary(self, active_id: str | None) -> dict[str, object]:
        matchups = {
            f"{projection.team} vs {projection.opponent}"
            for projection in self.projections
            if projection.opponent
        }
        return {
            "id": self.id,
            "label": self.label,
            "source": self.source,
            "season": self.season,
            "week": self.week,
            "imported_at": self.imported_at.isoformat(),
            "active": self.id == active_id,
            "player_count": len({(p.canonical_name or p.player_name).lower() for p in self.projections}),
            "projection_count": len(self.projections),
            "matchup_count": len(matchups),
        }


class ProjectionSnapshotStore:
    """Persist named projection imports, with exactly one active snapshot."""

    def __init__(self, path: Path = DEFAULT_SNAPSHOT_PATH) -> None:
        self.path = path
        self._lock = threading.RLock()

    def _read(self) -> tuple[str | None, list[ProjectionSnapshot]]:
        if not self.path.exists():
            return None, []
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(raw, dict) or raw.get("version") != 1:
                raise ValueError("unsupported snapshot version")
            snapshots: list[ProjectionSnapshot] = []
            for item in raw.get("snapshots", []):
                snapshots.append(
                    ProjectionSnapshot(
                        id=str(item["id"]),
                        label=str(item["label"]),
                        source=str(item["source"]),
                        season=int(item["season"]),
                        week=int(item["week"]),
                        imported_at=datetime.fromisoformat(item["imported_at"]),
                        projections=[PlayerProjection.model_validate(p) for p in item["projections"]],
                    )
                )
            return raw.get("active_id"), snapshots
        except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError, ValidationError):
            return None, []

    def _write(self, active_id: str | None, snapshots: list[ProjectionSnapshot]) -> None:
        payload = {
            "version": 1,
            "active_id": active_id,
            "snapshots": [
                {
                    "id": snapshot.id,
                    "label": snapshot.label,
                    "source": snapshot.source,
                    "season": snapshot.season,
                    "week": snapshot.week,
                    "imported_at": snapshot.imported_at.isoformat(),
                    "projections": [projection.model_dump(mode="json") for projection in snapshot.projections],
                }
                for snapshot in snapshots
            ],
        }
        serialized = json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = self.path.with_suffix(".tmp")
        temporary_path.write_text(serialized, encoding="utf-8")
        temporary_path.replace(self.path)

    def list_summaries(self) -> dict[str, object]:
        with self._lock:
            active_id, snapshots = self._read()
            ordered = sorted(snapshots, key=lambda item: item.imported_at, reverse=True)
            return {"active_id": active_id, "snapshots": [item.summary(active_id) for item in ordered]}

    def create(self, projections: list[PlayerProjection], *, label: str, source: str, season: int, week: int) -> ProjectionSnapshot:
        if not projections:
            raise ValueError("Cannot save an empty projection snapshot.")
        with self._lock:
            _, snapshots = self._read()
            snapshot = ProjectionSnapshot(
                id=str(uuid.uuid4()),
                label=label.strip() or f"{source} — {season} Week {week}",
                source=source.strip() or "Manual import",
                season=season,
                week=week,
                imported_at=datetime.now(timezone.utc),
                projections=projections,
            )
            snapshots.append(snapshot)
            self._write(snapshot.id, snapshots)
            return snapshot

    def get(self, snapshot_id: str) -> ProjectionSnapshot:
        with self._lock:
            _, snapshots = self._read()
            for snapshot in snapshots:
                if snapshot.id == snapshot_id:
                    return snapshot
        raise ProjectionSnapshotNotFoundError(snapshot_id)

    def activate(self, snapshot_id: str) -> ProjectionSnapshot:
        with self._lock:
            _, snapshots = self._read()
            selected = next((item for item in snapshots if item.id == snapshot_id), None)
            if not selected:
                raise ProjectionSnapshotNotFoundError(snapshot_id)
            self._write(snapshot_id, snapshots)
            return selected

    def delete(self, snapshot_id: str) -> None:
        with self._lock:
            active_id, snapshots = self._read()
            if active_id == snapshot_id:
                raise ValueError("Activate another projection set before deleting the active one.")
            remaining = [snapshot for snapshot in snapshots if snapshot.id != snapshot_id]
            if len(remaining) == len(snapshots):
                raise ProjectionSnapshotNotFoundError(snapshot_id)
            self._write(active_id, remaining)


projection_snapshot_store = ProjectionSnapshotStore()
