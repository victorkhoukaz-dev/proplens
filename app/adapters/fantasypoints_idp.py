"""Parse the IDP CSV exports without treating fantasy points as prop projections."""
from __future__ import annotations

import csv
import io
import math

from app.core.normalizer import PlayerNameNormalizer, TeamNormalizer
from app.schemas.projections import PlayerProjection, StatCategory


REQUIRED = {"NAME", "Position", "Team", "OPP", "TCK", "AST"}
POSITIONS = {"EDGE", "DL", "LB", "DB"}


def parse_idp_files(files: list[tuple[str, bytes]], *, season: int, week: int) -> tuple[list[PlayerProjection], int]:
    """Return one tackles-plus-assists mean per distinct player/team."""
    if not files or len(files) > 4:
        raise ValueError("Choose between one and four defensive CSV files.")
    players: dict[tuple[str, str], PlayerProjection] = {}
    duplicates = 0
    for filename, content in files:
        if not filename.lower().endswith(".csv"):
            raise ValueError(f"{filename}: choose a CSV file.")
        try:
            lines = content.decode("utf-8-sig").splitlines()
        except UnicodeDecodeError as exc:
            raise ValueError(f"{filename}: the CSV must be UTF-8 encoded.") from exc
        if len(lines) < 3:
            raise ValueError(f"{filename}: no defensive projection rows were found.")
        # FantasyPoints puts a grouped banner above the actual field names.
        header_index = next((i for i, line in enumerate(lines[:3]) if REQUIRED <= set(next(csv.reader([line])))), None)
        if header_index is None:
            raise ValueError(f"{filename}: expected NAME, Position, Team, OPP, TCK, and AST columns.")
        reader = csv.DictReader(io.StringIO("\n".join(lines[header_index:])))
        file_count = 0
        for number, row in enumerate(reader, start=header_index + 2):
            name = (row.get("NAME") or "").strip()
            if not name:
                continue
            position = (row.get("Position") or "").strip().upper()
            team_raw = (row.get("Team") or "").strip()
            opponent_raw = (row.get("OPP") or "").strip().lstrip("@")
            if position not in POSITIONS or not team_raw or not opponent_raw:
                raise ValueError(f"{filename}, row {number}: position, team, or opponent is missing or unsupported.")
            try:
                tackles = float(row["TCK"])
                assists = float(row["AST"])
            except (TypeError, ValueError) as exc:
                raise ValueError(f"{filename}, row {number}: TCK and AST must be numbers.") from exc
            if not all(math.isfinite(value) and value >= 0 for value in (tackles, assists)):
                raise ValueError(f"{filename}, row {number}: TCK and AST must be nonnegative finite numbers.")
            team = TeamNormalizer.canonical_team(team_raw)
            opponent = TeamNormalizer.canonical_team(opponent_raw)
            canonical_name = PlayerNameNormalizer.clean_name(name)
            projection = PlayerProjection(
                player_name=name,
                canonical_name=canonical_name,
                team=team,
                opponent=opponent,
                position=position,
                stat_category=StatCategory.TACKLES_ASSISTS,
                projection_mean=round(tackles + assists, 4),
                source="fantasypoints_idp",
                season=season,
                week=week,
                metadata={"tackles": tackles, "assists": assists},
            )
            key = (canonical_name.lower(), team)
            old = players.get(key)
            if old is not None:
                if (old.projection_mean, old.position, old.opponent, old.metadata) != (projection.projection_mean, projection.position, projection.opponent, projection.metadata):
                    raise ValueError(f"{filename}, row {number}: conflicting duplicate projection for {name} ({team}).")
                duplicates += 1
            else:
                players[key] = projection
            file_count += 1
        if not file_count:
            raise ValueError(f"{filename}: no defensive players were found.")
    return list(players.values()), duplicates
