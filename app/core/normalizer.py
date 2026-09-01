"""
app/core/normalizer.py - Production-Grade Player & Team Normalization Engine
NFL +EV Betting Application (Bet365 Canada vs. Sharp Devig & FantasyPoints)
"""

from __future__ import annotations

import functools
import logging
import re
import unicodedata
from typing import Any, Dict, List, Optional, Sequence, Set

logger = logging.getLogger(__name__)

try:
    from rapidfuzz import fuzz
    RAPIDFUZZ_AVAILABLE = True
except ImportError:  # pragma: no cover
    import difflib
    RAPIDFUZZ_AVAILABLE = False
    logger.warning("RapidFuzz not installed. Falling back to difflib for fuzzy matching.")

SUFFIX_PATTERN = re.compile(r'\b(jr|sr|ii|iii|iv|v)\b\.?', re.IGNORECASE)
APOSTROPHE_PATTERN = re.compile(r"['`’´]")
HYPHEN_SLASH_PATTERN = re.compile(r"[-_/]")
PUNCT_CLEAN_PATTERN = re.compile(r'[^\w\s]')
SPACED_INITIALS_PATTERN = re.compile(r'\b([a-z])\s+([a-z])\b', re.IGNORECASE)
WHITESPACE_PATTERN = re.compile(r'\s+')

FIRST_NAME_MAP: Dict[str, str] = {
    "gabe": "gabriel",
    "mitch": "mitchell",
    "josh": "joshua",
    "cam": "cameron",
    "pat": "patrick",
    "matt": "matthew",
    "ken": "kenneth",
    "dan": "daniel",
    "danny": "daniel",
    "mike": "michael",
    "tony": "anthony",
    "alex": "alexander",
    "zach": "zachary",
    "zack": "zachary",
    "nick": "nicholas",
    "nate": "nathaniel",
    "will": "william",
    "bill": "william",
    "billy": "william",
    "ben": "benjamin",
    "benny": "benjamin",
    "sam": "samuel",
    "chris": "christopher",
    "scotty": "scott",
    "jeff": "jeffery",
    "rob": "robert",
    "robby": "robert",
    "robbie": "robert",
    "bobby": "robert",
    "tom": "thomas",
    "tommy": "thomas",
    "tim": "timothy",
    "dave": "david",
    "andy": "andrew",
    "drew": "andrew",
    "greg": "gregory",
    "jim": "james",
    "jimmy": "james",
    "joe": "joseph",
    "joey": "joseph",
    "jon": "jonathan",
    "jonny": "jonathan",
    "johnny": "john",
}

PLAYER_ALIAS_MAP: Dict[str, str] = {
    "hollywood brown": "marquise brown",
    "marquise hollywood brown": "marquise brown",
    "chig okonkwo": "chigoziem okonkwo",
    "chigoziem chig okonkwo": "chigoziem okonkwo",
    "tank dell": "nathaniel dell",
    "nathaniel tank dell": "nathaniel dell",
    "robbie anderson": "chosen anderson",
    "robby anderson": "chosen anderson",
    "robbie chosen": "chosen anderson",
    "chosen anderson": "chosen anderson",
    "pj walker": "phillip walker",
    "phillip pj walker": "phillip walker",
    "ray ray mccloud": "rayray mccloud",
    "rayray mccloud": "rayray mccloud",
    "ceedee lamb": "ceedee lamb",
    "cedarian lamb": "ceedee lamb",
    "cdee lamb": "ceedee lamb",
    "ha ha clinton dix": "haha clinton dix",
    "haha clinton dix": "haha clinton dix",
    "deandre swift": "dandre swift",
    "dandre swift": "dandre swift",
    "d j moore": "dj moore",
    "dj moore": "dj moore",
    "a j brown": "aj brown",
    "aj brown": "aj brown",
    "c j stroud": "cj stroud",
    "cj stroud": "cj stroud",
    "t j hockenson": "tj hockenson",
    "tj hockenson": "tj hockenson",
    "j k dobbins": "jk dobbins",
    "jk dobbins": "jk dobbins",
    "k j osborn": "kj osborn",
    "kj osborn": "kj osborn",
    "d k metcalf": "dk metcalf",
    "dk metcalf": "dk metcalf",
    "trequan smith": "trequan smith",
    "tre quan smith": "trequan smith",
    "scotty miller": "scott miller",
    "scott miller": "scott miller",
    "jeff wilson": "jeffery wilson",
    "jeffery wilson": "jeffery wilson",
    "trey sermon": "trey sermon",
    "samaje perine": "samaje perine",
    "kadarius toney": "kadarius toney",
}


class PlayerNameNormalizer:
    """
    5-step Player Name Normalizer & Fuzzy Matcher with nickname expansions,
    suffix stripping, and position/team guardrails.
    """

    @staticmethod
    @functools.lru_cache(maxsize=4096)
    def clean_name(raw_name: str | None) -> str:
        """
        Deterministic 5-step name normalization:
        1. Inversion check ('Mahomes, Patrick' -> 'Patrick Mahomes')
        2. Unicode NFKD -> ASCII decomposition
        3. Lowercase & outer whitespace strip
        4. Generational suffix removal ('Jr', 'Sr', 'II', 'III', 'IV', 'V')
        5. Punctuation removal & spaced initials collapse ('A.J.' -> 'aj')
        6. Nickname & alias mapping (PLAYER_ALIAS_MAP & FIRST_NAME_MAP)
        """
        if not raw_name or not isinstance(raw_name, str):
            return ""

        name = raw_name.strip()
        # Inversion check
        if "," in name:
            parts = [p.strip() for p in name.split(",") if p.strip()]
            if len(parts) == 2:
                if SUFFIX_PATTERN.match(parts[1]):
                    name = f"{parts[0]} {parts[1]}"
                else:
                    name = f"{parts[1]} {parts[0]}"
            elif len(parts) >= 3:
                name = f"{parts[1]} {parts[0]} {parts[2]}"

        # 1. Unicode NFKD to ASCII
        name = unicodedata.normalize("NFKD", name).encode("ASCII", "ignore").decode("utf-8")
        # 2. Lowercase and strip
        name = name.lower().strip()
        # 3. Suffix removal
        name = SUFFIX_PATTERN.sub("", name).strip()
        # 4. Punctuation removal & spaced initials collapse
        name = APOSTROPHE_PATTERN.sub("", name)
        name = HYPHEN_SLASH_PATTERN.sub(" ", name)
        name = PUNCT_CLEAN_PATTERN.sub("", name)
        name = SPACED_INITIALS_PATTERN.sub(r"\1\2", name)
        name = WHITESPACE_PATTERN.sub(" ", name).strip()

        # 5. Nickname & Alias Mapping
        if name in PLAYER_ALIAS_MAP:
            name = PLAYER_ALIAS_MAP[name]
        else:
            tokens = name.split(" ")
            if len(tokens) >= 2:
                first, rest = tokens[0], tokens[1:]
                if first in FIRST_NAME_MAP:
                    name = f"{FIRST_NAME_MAP[first]} {' '.join(rest)}"

        return name

    @staticmethod
    def match_player(
        target_name: str,
        candidate_pool: Sequence[str],
        position: Optional[str] = None,
        team: Optional[str] = None,
        threshold: float = 85.0,
        candidate_metadata: Optional[Dict[str, Dict[str, Any]]] = None,
    ) -> Optional[str]:
        """
        Match target player name against a candidate pool using exact fast-path,
        RapidFuzz token similarity, and team/position guardrails.
        """
        if not target_name or not candidate_pool:
            return None

        clean_target = PlayerNameNormalizer.clean_name(target_name)
        if not clean_target:
            return None

        norm_team = TeamNormalizer.canonical_team(team) if team else None
        norm_pos = position.upper().strip() if position else None

        # Fast path: exact cleaned match
        exact_matches: List[str] = []
        for cand in candidate_pool:
            clean_cand = PlayerNameNormalizer.clean_name(cand)
            if clean_cand == clean_target:
                if candidate_metadata and cand in candidate_metadata:
                    meta = candidate_metadata[cand]
                    if norm_team and "team" in meta:
                        if TeamNormalizer.canonical_team(meta["team"]) != norm_team:
                            continue
                    if norm_pos and "position" in meta:
                        if str(meta["position"]).upper().strip() != norm_pos:
                            continue
                exact_matches.append(cand)

        if len(exact_matches) == 1:
            return exact_matches[0]
        elif len(exact_matches) > 1:
            return exact_matches[0]

        # Fuzzy matching
        best_cand: Optional[str] = None
        best_score: float = -1.0
        second_best_score: float = -1.0

        for cand in candidate_pool:
            clean_cand = PlayerNameNormalizer.clean_name(cand)
            if not clean_cand:
                continue

            if candidate_metadata and cand in candidate_metadata:
                meta = candidate_metadata[cand]
                if norm_team and "team" in meta:
                    if TeamNormalizer.canonical_team(meta["team"]) != norm_team:
                        continue
                if norm_pos and "position" in meta:
                    if str(meta["position"]).upper().strip() != norm_pos:
                        continue

            if RAPIDFUZZ_AVAILABLE:
                sort_score = float(fuzz.token_sort_ratio(clean_target, clean_cand))
                set_score = float(fuzz.token_set_ratio(clean_target, clean_cand))
                score = max(sort_score, set_score)
            else:
                seq = difflib.SequenceMatcher(None, clean_target, clean_cand)
                score = seq.ratio() * 100.0

            if score > best_score:
                second_best_score = best_score
                best_score = score
                best_cand = cand
            elif score > second_best_score:
                second_best_score = score

        if best_cand is not None and best_score >= threshold:
            if second_best_score > 0 and (best_score - second_best_score) < 1.0 and candidate_metadata is None:
                return None
            return best_cand

        return None


NFL_CANONICAL_TEAMS: Set[str] = {
    "ARI", "ATL", "BAL", "BUF", "CAR", "CHI", "CIN", "CLE",
    "DAL", "DEN", "DET", "GB", "HOU", "IND", "JAX", "KC",
    "LAC", "LAR", "LV", "MIA", "MIN", "NE", "NO", "NYG",
    "NYJ", "PHI", "PIT", "SEA", "SF", "TB", "TEN", "WAS"
}

NFL_TEAM_LOOKUP: Dict[str, str] = {
    # AFC East
    "BUF": "BUF", "BUFFALO": "BUF", "BUFFALO BILLS": "BUF", "BILLS": "BUF",
    "MIA": "MIA", "MIAMI": "MIA", "MIAMI DOLPHINS": "MIA", "DOLPHINS": "MIA",
    "NE": "NE", "NWE": "NE", "NEP": "NE", "NEW ENGLAND": "NE", "NEW ENGLAND PATRIOTS": "NE", "PATRIOTS": "NE", "BOSTON": "NE",
    "NYJ": "NYJ", "NEW YORK JETS": "NYJ", "NY JETS": "NYJ", "JETS": "NYJ",

    # AFC North
    "BAL": "BAL", "BALTIMORE": "BAL", "BALTIMORE RAVENS": "BAL", "RAVENS": "BAL",
    "CIN": "CIN", "CINCINNATI": "CIN", "CINCINNATI BENGALS": "CIN", "BENGALS": "CIN", "CINCY": "CIN",
    "CLE": "CLE", "CLEVELAND": "CLE", "CLEVELAND BROWNS": "CLE", "BROWNS": "CLE",
    "PIT": "PIT", "PITTSBURGH": "PIT", "PITTSBURGH STEELERS": "PIT", "STEELERS": "PIT", "PITT": "PIT",

    # AFC South
    "HOU": "HOU", "HOUSTON": "HOU", "HOUSTON TEXANS": "HOU", "TEXANS": "HOU",
    "IND": "IND", "INDIANAPOLIS": "IND", "INDIANAPOLIS COLTS": "IND", "COLTS": "IND", "INDY": "IND",
    "JAX": "JAX", "JAC": "JAX", "JAG": "JAX", "JACKSONVILLE": "JAX", "JACKSONVILLE JAGUARS": "JAX", "JAGUARS": "JAX",
    "TEN": "TEN", "TENNESSEE": "TEN", "TENNESSEE TITANS": "TEN", "TITANS": "TEN", "TENNESSEE OILERS": "TEN", "OILERS": "TEN",

    # AFC West
    "DEN": "DEN", "DENVER": "DEN", "DENVER BRONCOS": "DEN", "BRONCOS": "DEN",
    "KC": "KC", "KAN": "KC", "KCC": "KC", "KANSAS CITY": "KC", "KANSAS CITY CHIEFS": "KC", "CHIEFS": "KC",
    "LV": "LV", "LVR": "LV", "OAK": "LV", "LAS VEGAS": "LV", "LAS VEGAS RAIDERS": "LV", "RAIDERS": "LV", "OAKLAND RAIDERS": "LV", "OAKLAND": "LV",
    "LAC": "LAC", "SD": "LAC", "SDC": "LAC", "LOS ANGELES CHARGERS": "LAC", "LA CHARGERS": "LAC", "CHARGERS": "LAC", "SAN DIEGO CHARGERS": "LAC", "SAN DIEGO": "LAC",

    # NFC East
    "DAL": "DAL", "DALLAS": "DAL", "DALLAS COWBOYS": "DAL", "COWBOYS": "DAL",
    "NYG": "NYG", "NEW YORK GIANTS": "NYG", "NY GIANTS": "NYG", "GIANTS": "NYG",
    "PHI": "PHI", "PHILADELPHIA": "PHI", "PHILADELPHIA EAGLES": "PHI", "EAGLES": "PHI", "PHILLY": "PHI",
    "WAS": "WAS", "WSH": "WAS", "WFT": "WAS", "WASHINGTON": "WAS", "WASHINGTON COMMANDERS": "WAS", "COMMANDERS": "WAS", "WASHINGTON FOOTBALL TEAM": "WAS", "REDSKINS": "WAS",

    # NFC North
    "CHI": "CHI", "CHICAGO": "CHI", "CHICAGO BEARS": "CHI", "BEARS": "CHI",
    "DET": "DET", "DETROIT": "DET", "DETROIT LIONS": "DET", "LIONS": "DET",
    "GB": "GB", "GNB": "GB", "GBP": "GB", "GREEN BAY": "GB", "GREEN BAY PACKERS": "GB", "PACKERS": "GB",
    "MIN": "MIN", "MINNESOTA": "MIN", "MINNESOTA VIKINGS": "MIN", "VIKINGS": "MIN",

    # NFC South
    "ATL": "ATL", "ATLANTA": "ATL", "ATLANTA FALCONS": "ATL", "FALCONS": "ATL",
    "CAR": "CAR", "CAROLINA": "CAR", "CAROLINA PANTHERS": "CAR", "PANTHERS": "CAR",
    "NO": "NO", "NOR": "NO", "NOS": "NO", "NEW ORLEANS": "NO", "NEW ORLEANS SAINTS": "NO", "SAINTS": "NO", "NOLA": "NO",
    "TB": "TB", "TAM": "TB", "TBB": "TB", "TAMPA BAY": "TB", "TAMPA BAY BUCCANEERS": "TB", "BUCCANEERS": "TB", "BUCS": "TB", "TAMPA": "TB",

    # NFC West
    "ARI": "ARI", "ARZ": "ARI", "ARIZ": "ARI", "ARIZONA": "ARI", "ARIZONA CARDINALS": "ARI", "CARDINALS": "ARI", "PHOENIX CARDINALS": "ARI", "PHO": "ARI",
    "LAR": "LAR", "LA RAMS": "LAR", "LOS ANGELES RAMS": "LAR", "RAMS": "LAR", "ST LOUIS RAMS": "LAR", "STL": "LAR",
    "SF": "SF", "SFO": "SF", "SAN FRANCISCO": "SF", "SAN FRANCISCO 49ERS": "SF", "49ERS": "SF", "NINERS": "SF",
    "SEA": "SEA", "SEATTLE": "SEA", "SEATTLE SEAHAWKS": "SEA", "SEAHAWKS": "SEA",
}


class TeamNormalizer:
    """
    Canonical 32-team NFL Abbreviation Normalizer.
    Resolves city names, nicknames, and alternative abbreviations to canonical 2-3 letter codes.
    """

    @staticmethod
    @functools.lru_cache(maxsize=512)
    def canonical_team(raw_team: str | None) -> str:
        """
        Normalize raw team string to 32-team canonical code (e.g. 'KAN' -> 'KC', 'Tampa Bay' -> 'TB').
        """
        if not raw_team or not isinstance(raw_team, str):
            return ""

        clean_team = unicodedata.normalize("NFKD", raw_team).encode("ASCII", "ignore").decode("utf-8")
        clean_team = clean_team.upper().strip()

        if clean_team in NFL_CANONICAL_TEAMS:
            return clean_team

        clean_team_lookup = re.sub(r"[^\w\s]", "", clean_team)
        clean_team_lookup = re.sub(r"\s+", " ", clean_team_lookup).strip()

        if clean_team_lookup in NFL_TEAM_LOOKUP:
            return NFL_TEAM_LOOKUP[clean_team_lookup]

        if clean_team in NFL_TEAM_LOOKUP:
            return NFL_TEAM_LOOKUP[clean_team]

        return clean_team
