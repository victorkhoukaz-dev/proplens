"""
E2E Test Suite Harness and Fixtures (Standalone & Pytest Compatible)

Provides deterministic offline execution, reference domain implementations,
mock adapters, and test fixtures for all 4 verification tiers.
"""

import os
import sys
import math
import json
import csv
import re
import unicodedata
import asyncio
from enum import Enum
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple, Union
from statistics import NormalDist

# Workspace paths
WORKSPACE_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
SAMPLE_DATA_DIR = os.path.join(WORKSPACE_ROOT, "sample_data")
FANTASYPOINTS_CSV_PATH = os.path.join(SAMPLE_DATA_DIR, "fantasypoints_sample.csv")
ODDS_SNAPSHOT_JSON_PATH = os.path.join(SAMPLE_DATA_DIR, "odds_snapshot_sample.json")
ODDS_SAMPLE_CSV_PATH = os.path.join(SAMPLE_DATA_DIR, "odds_sample.csv")


# ==============================================================================
# 1. DOMAIN ENUMS & SCHEMAS
# ==============================================================================

class MarketType(str, Enum):
    PASSING_YARDS = "player_pass_yds"
    PASSING_TDS = "player_pass_tds"
    PASSING_INTS = "player_pass_interceptions"
    RUSHING_YARDS = "player_rush_yds"
    RECEIVING_YARDS = "player_reception_yds"
    RECEPTIONS = "player_receptions"
    ANYTIME_TD = "player_anytime_td"
    MONEYLINE = "h2h"
    POINT_SPREAD = "spreads"
    GAME_TOTAL = "totals"

    @classmethod
    def from_string(cls, val: str) -> "MarketType":
        s = val.lower().strip().replace(" ", "_").replace("-", "_")
        aliases = {
            "player_pass_yds": cls.PASSING_YARDS,
            "pass_yds": cls.PASSING_YARDS,
            "passing_yards": cls.PASSING_YARDS,
            "player_pass_tds": cls.PASSING_TDS,
            "pass_tds": cls.PASSING_TDS,
            "passing_tds": cls.PASSING_TDS,
            "player_pass_interceptions": cls.PASSING_INTS,
            "player_pass_ints": cls.PASSING_INTS,
            "pass_ints": cls.PASSING_INTS,
            "interceptions": cls.PASSING_INTS,
            "player_rush_yds": cls.RUSHING_YARDS,
            "rush_yds": cls.RUSHING_YARDS,
            "rushing_yards": cls.RUSHING_YARDS,
            "player_reception_yds": cls.RECEIVING_YARDS,
            "player_rec_yds": cls.RECEIVING_YARDS,
            "rec_yds": cls.RECEIVING_YARDS,
            "receiving_yards": cls.RECEIVING_YARDS,
            "player_receptions": cls.RECEPTIONS,
            "receptions": cls.RECEPTIONS,
            "catches": cls.RECEPTIONS,
            "player_anytime_td": cls.ANYTIME_TD,
            "anytime_td": cls.ANYTIME_TD,
            "anytime_touchdown": cls.ANYTIME_TD,
            "h2h": cls.MONEYLINE,
            "moneyline": cls.MONEYLINE,
            "spreads": cls.POINT_SPREAD,
            "spread": cls.POINT_SPREAD,
            "point_spread": cls.POINT_SPREAD,
            "totals": cls.GAME_TOTAL,
            "total": cls.GAME_TOTAL,
            "game_total": cls.GAME_TOTAL,
        }
        if s in aliases:
            return aliases[s]
        raise ValueError(f"Unknown market identifier: {val}")


class PlayerPosition(str, Enum):
    QB = "QB"
    RB = "RB"
    WR = "WR"
    TE = "TE"
    K = "K"
    DEF = "DEF"
    EDGE = "EDGE"


class DevigMethod(str, Enum):
    MULTIPLICATIVE = "multiplicative"
    ADDITIVE = "additive"
    POWER = "power"
    SHIN = "shin"


class DistributionType(str, Enum):
    LOG_NORMAL = "log_normal"
    CALIBRATED_NORMAL = "calibrated_normal"
    POISSON = "poisson"
    NEGATIVE_BINOMIAL = "negative_binomial"


@dataclass(frozen=True)
class OddsValue:
    american: int
    decimal: float
    implied_prob: float

    @classmethod
    def from_american(cls, american: int) -> "OddsValue":
        if american == 0 or (-100 < american < 100):
            raise ValueError(f"Invalid American odds: {american}. Cannot be between -100 and +100 or 0.")
        if american > 0:
            dec = 1.0 + (american / 100.0)
        else:
            dec = 1.0 + (100.0 / abs(american))
        dec = round(dec, 4)
        prob = round(1.0 / dec, 6)
        return cls(american=american, decimal=dec, implied_prob=prob)

    @classmethod
    def from_decimal(cls, decimal: float) -> "OddsValue":
        if decimal <= 1.000:
            raise ValueError(f"Invalid Decimal odds: {decimal}. Must be >= 1.001.")
        if decimal >= 2.0:
            ame = int(round((decimal - 1.0) * 100.0))
        else:
            ame = int(round(-100.0 / (decimal - 1.0)))
        prob = round(1.0 / decimal, 6)
        return cls(american=ame, decimal=round(decimal, 4), implied_prob=prob)


@dataclass
class Player:
    player_id: str
    raw_name: str
    normalized_name: str
    first_name: str
    last_name: str
    team: str
    position: PlayerPosition
    suffix: Optional[str] = None


@dataclass
class Event:
    event_id: str
    season: int
    week: int
    home_team: str
    away_team: str
    commence_time: str
    is_live: bool = False


@dataclass
class MarketOffer:
    offer_id: str
    event_id: str
    bookmaker: str
    market_type: MarketType
    player_name: Optional[str]
    side: str  # "Over", "Under", "Yes", "No", "Home", "Away"
    point: float
    odds: OddsValue
    is_suspended: bool = False
    timestamp: str = ""


@dataclass
class PlayerProjection:
    player_id: str
    raw_name: str
    normalized_name: str
    team: str
    position: PlayerPosition
    opponent: str
    season: int = 2026
    week: int = 1
    pass_att: float = 0.0
    pass_cmp: float = 0.0
    pass_yds: float = 0.0
    pass_td: float = 0.0
    pass_int: float = 0.0
    rush_att: float = 0.0
    rush_yds: float = 0.0
    rush_td: float = 0.0
    targets: float = 0.0
    receptions: float = 0.0
    rec_yds: float = 0.0
    rec_td: float = 0.0
    anytime_td_mean: float = 0.0
    fantasy_points: float = 0.0
    source: str = "FantasyPoints.com"

    def __post_init__(self):
        if self.anytime_td_mean == 0.0 and (self.rush_td > 0 or self.rec_td > 0):
            self.anytime_td_mean = round(self.rush_td + self.rec_td, 2)


@dataclass
class DevigResult:
    method: DevigMethod
    fair_implied_probabilities: List[float]
    fair_decimal_odds: List[float]
    fair_american_odds: List[int]
    overround: float
    raw_probabilities: List[float]
    z_parameter: Optional[float] = None
    warning: Optional[str] = None


@dataclass
class DistributionResult:
    prob_over: float
    prob_under: float
    prob_push: float
    conditional_prob_over: float
    conditional_prob_under: float
    fair_decimal_over: float
    fair_decimal_under: float
    distribution_type: DistributionType


@dataclass
class EVResult:
    market_implied_ev: Optional[float]
    model_implied_ev: Optional[float]
    blended_ev: float
    blended_win_prob: float
    quarter_kelly_fraction: float
    quarter_kelly_stake: float
    half_kelly_stake: float
    full_kelly_stake: float
    recommended_stake: float
    is_capped: bool = False


@dataclass
class MatchedEVOpportunity:
    opportunity_id: str
    player_name: str
    team: str
    opponent: str
    market_type: MarketType
    side: str
    line: float
    bet365_decimal: float
    bet365_american: int
    sharp_benchmark_book: str
    sharp_fair_decimal: Optional[float]
    model_fair_prob: Optional[float]
    market_ev_percent: Optional[float]
    model_ev_percent: Optional[float]
    blended_ev_percent: float
    quarter_kelly_stake: float
    recommended_stake: float
    prob_push: float = 0.0
    status: str = "ACTIVE"


# ==============================================================================
# 2. NORMALIZATION ENGINES (F03, F04)
# ==============================================================================

class TeamNormalizer:
    CANONICAL_TEAMS = {
        "ARI", "ATL", "BAL", "BUF", "CAR", "CHI", "CIN", "CLE",
        "DAL", "DEN", "DET", "GB", "HOU", "IND", "JAX", "KC",
        "LV", "LAC", "LAR", "MIA", "MIN", "NE", "NO", "NYG",
        "NYJ", "PHI", "PIT", "SF", "SEA", "TB", "TEN", "WAS"
    }

    TEAM_ALIASES = {
        "KAN": "KC", "KANSAS CITY": "KC", "KANSAS CITY CHIEFS": "KC", "CHIEFS": "KC",
        "WSH": "WAS", "WFT": "WAS", "WASHINGTON": "WAS", "WASHINGTON COMMANDERS": "WAS", "COMMANDERS": "WAS", "REDSKINS": "WAS",
        "LVR": "LV", "OAK": "LV", "LAS VEGAS": "LV", "LAS VEGAS RAIDERS": "LV", "OAKLAND RAIDERS": "LV", "RAIDERS": "LV",
        "TAM": "TB", "TAMPA BAY": "TB", "TAMPA BAY BUCCANEERS": "TB", "BUCCANEERS": "TB", "BUCS": "TB",
        "NOR": "NO", "NEW ORLEANS": "NO", "NEW ORLEANS SAINTS": "NO", "SAINTS": "NO",
        "GNB": "GB", "GREEN BAY": "GB", "GREEN BAY PACKERS": "GB", "PACKERS": "GB",
        "SFO": "SF", "SAN FRANCISCO": "SF", "SAN FRANCISCO 49ERS": "SF", "49ERS": "SF", "NINERS": "SF",
        "ARZ": "ARI", "ARIZONA": "ARI", "ARIZONA CARDINALS": "ARI", "CARDINALS": "ARI",
        "JAC": "JAX", "JACKSONVILLE": "JAX", "JACKSONVILLE JAGUARS": "JAX", "JAGUARS": "JAGS",
        "LA": "LAR", "LOS ANGELES RAMS": "LAR", "RAMS": "LAR",
        "LOS ANGELES CHARGERS": "LAC", "SD": "LAC", "SAN DIEGO CHARGERS": "LAC", "CHARGERS": "LAC",
        "NEW YORK GIANTS": "NYG", "GIANTS": "NYG",
        "NEW YORK JETS": "NYJ", "JETS": "NYJ",
        "NWE": "NE", "NEW ENGLAND": "NE", "NEW ENGLAND PATRIOTS": "NE", "PATRIOTS": "NE", "PATS": "NE",
        "BALTIMORE": "BAL", "BALTIMORE RAVENS": "BAL", "RAVENS": "BAL",
        "BUFFALO": "BUF", "BUFFALO BILLS": "BUF", "BILLS": "BUF",
        "CAROLINA": "CAR", "CAROLINA PANTHERS": "CAR", "PANTHERS": "CAR",
        "CHICAGO": "CHI", "CHICAGO BEARS": "CHI", "BEARS": "CHI",
        "CINCINNATI": "CIN", "CINCINNATI BENGALS": "CIN", "BENGALS": "CIN",
        "CLEVELAND": "CLE", "CLEVELAND BROWNS": "CLE", "BROWNS": "CLE",
        "DALLAS": "DAL", "DALLAS COWBOYS": "DAL", "COWBOYS": "DAL",
        "DENVER": "DEN", "DENVER BRONCOS": "DEN", "BRONCOS": "DEN",
        "DETROIT": "DET", "DETROIT LIONS": "DET", "LIONS": "DET",
        "HOUSTON": "HOU", "HOUSTON TEXANS": "HOU", "TEXANS": "HOU",
        "INDIANAPOLIS": "IND", "INDIANAPOLIS COLTS": "IND", "COLTS": "IND",
        "MIAMI": "MIA", "MIAMI DOLPHINS": "MIA", "DOLPHINS": "MIA", "FINS": "MIA",
        "MINNESOTA": "MIN", "MINNESOTA VIKINGS": "MIN", "VIKINGS": "MIN",
        "PHILADELPHIA": "PHI", "PHILADELPHIA EAGLES": "PHI", "EAGLES": "PHI",
        "PITTSBURGH": "PIT", "PITTSBURGH STEELERS": "PIT", "STEELERS": "PIT",
        "SEATTLE": "SEA", "SEATTLE SEAHAWKS": "SEA", "SEAHAWKS": "SEA",
        "TENNESSEE": "TEN", "TENNESSEE TITANS": "TEN", "TITANS": "TEN",
    }

    @classmethod
    def canonical_team(cls, raw_team: str) -> str:
        if not raw_team:
            return ""
        clean = raw_team.strip().upper()
        if clean in cls.CANONICAL_TEAMS:
            return clean
        if clean in cls.TEAM_ALIASES:
            return cls.TEAM_ALIASES[clean]
        # Return uppercase sanitized input if not in explicit alias dictionary
        return clean


class PlayerNameNormalizer:
    NICKNAMES = {
        "gabe davis": "gabriel davis",
        "mitch trubisky": "mitchell trubisky",
        "cam akers": "cameron akers",
        "hollywood brown": "marquise brown",
        "marquise hollywood brown": "marquise brown",
        "josh palmer": "joshua palmer",
        "chig okonkwo": "chigoziem okonkwo",
        "chigoziem chig okonkwo": "chigoziem okonkwo",
        "robby anderson": "chosen anderson",
        "robbie chosen": "chosen anderson",
        "chosen anderson": "chosen anderson",
        "dj moore": "dj moore",
        "d j moore": "dj moore",
        "aj brown": "aj brown",
        "a j brown": "aj brown",
        "cj stroud": "cj stroud",
        "c j stroud": "cj stroud",
        "pj walker": "phillip walker",
        "phillip pj walker": "phillip walker",
        "ray ray mccloud": "rayray mccloud",
        "scotty miller": "scott miller",
        "jeff wilson": "jeffery wilson",
        "jeffery wilson": "jeffery wilson",
        "trey sermon": "trey sermon",
        "samaje perine": "samaje perine",
        "kadarius toney": "kadarius toney",
    }

    SUFFIX_PATTERN = re.compile(r"\b(jr\.?|sr\.?|ii|iii|iv|v)\b", re.IGNORECASE)

    @classmethod
    def clean_name(cls, raw_name: Optional[str]) -> Tuple[str, Optional[str]]:
        if not raw_name or not str(raw_name).strip():
            return "", None
        
        # Step 1: Unicode NFKD decomposition
        text = unicodedata.normalize("NFKD", str(raw_name))
        text = "".join(c for c in text if not unicodedata.combining(c)).strip()
        
        # Step 2: Extract Suffix
        suffix = None
        match = cls.SUFFIX_PATTERN.search(text)
        if match:
            suffix = match.group(0).replace(".", "").upper()
            text = cls.SUFFIX_PATTERN.sub("", text)
            
        # Step 3: Remove punctuation and special characters
        text = re.sub(r"[^\w\s]", "", text)
        text = re.sub(r"\s+", " ", text).strip().lower()
        
        # Step 4: Nickname Expansion
        if text in cls.NICKNAMES:
            text = cls.NICKNAMES[text]
            
        return text, suffix

    @classmethod
    def match_player(
        cls,
        target_name: str,
        candidate_pool: List[Union[str, Dict[str, Any]]],
        position: Optional[str] = None,
        threshold: float = 85.0
    ) -> Optional[str]:
        target_clean, _ = cls.clean_name(target_name)
        if not target_clean:
            return None

        best_match = None
        highest_score = 0.0

        for cand in candidate_pool:
            if isinstance(cand, dict):
                c_name = cand.get("name", "")
                c_pos = cand.get("pos") or cand.get("position")
                if position and c_pos and str(c_pos).upper() != str(position).upper():
                    continue
            else:
                c_name = str(cand)

            c_clean, _ = cls.clean_name(c_name)
            if not c_clean:
                continue

            # Exact match
            if target_clean == c_clean:
                return c_name

            # Substring / Token matching score
            s1 = set(target_clean.split())
            s2 = set(c_clean.split())
            if s1 == s2:
                return c_name
            
            # Simple Levenshtein / Jaccard similarity fallback
            intersection = len(s1 & s2)
            union = len(s1 | s2)
            jaccard = (intersection / union) * 100.0 if union > 0 else 0.0
            
            # Char level similarity
            char_sim = 100.0 * (1.0 - (abs(len(target_clean) - len(c_clean)) / max(len(target_clean), len(c_clean), 1)))
            score = 0.7 * jaccard + 0.3 * char_sim
            
            if score > highest_score:
                highest_score = score
                best_match = c_name

        if highest_score >= threshold:
            return best_match
        return None


# ==============================================================================
# 3. DEVIGGING ENGINE (F06, F07, F08, F09)
# ==============================================================================

class DevigEngine:
    @staticmethod
    def american_to_decimal(american: int) -> float:
        return OddsValue.from_american(american).decimal

    @staticmethod
    def decimal_to_american(decimal: float) -> int:
        return OddsValue.from_decimal(decimal).american

    @classmethod
    def devig(cls, decimal_odds: List[float], method: DevigMethod = DevigMethod.SHIN) -> DevigResult:
        if len(decimal_odds) < 2:
            raise ValueError(f"Devigging requires at least 2 outcomes, got {len(decimal_odds)}")
        for d in decimal_odds:
            if d <= 1.0:
                raise ValueError(f"Decimal odds must be strictly > 1.0, got {d}")

        raw_probs = [1.0 / d for d in decimal_odds]
        overround = sum(raw_probs)

        # Check for perfect vig-free or arbitrage
        if math.isclose(overround, 1.0, rel_tol=1e-5, abs_tol=1e-5):
            probs = raw_probs
            return cls._build_result(method, probs, overround, raw_probs, z=0.0)

        if method == DevigMethod.MULTIPLICATIVE:
            probs = [q / overround for q in raw_probs]
            return cls._build_result(method, probs, overround, raw_probs)

        elif method == DevigMethod.ADDITIVE:
            margin = (overround - 1.0) / len(decimal_odds)
            probs = [q - margin for q in raw_probs]
            if any(p <= 0.0 for p in probs):
                # Boundary guardrail fallback to multiplicative
                probs = [q / overround for q in raw_probs]
                res = cls._build_result(method, probs, overround, raw_probs)
                res.warning = "Additive margin produced non-positive probability; fell back to Multiplicative."
                return res
            return cls._build_result(method, probs, overround, raw_probs)

        elif method == DevigMethod.POWER:
            # Solve sum(q_i^k) = 1.0
            def power_obj(k: float) -> float:
                return sum(math.pow(q, k) for q in raw_probs) - 1.0

            low, high = 0.5, 50.0
            for _ in range(50):
                mid = (low + high) / 2.0
                val = power_obj(mid)
                if abs(val) < 1e-10:
                    break
                if val > 0:
                    low = mid
                else:
                    high = mid
            k_opt = (low + high) / 2.0
            unnorm = [math.pow(q, k_opt) for q in raw_probs]
            s = sum(unnorm)
            probs = [p / s for p in unnorm]
            return cls._build_result(method, probs, overround, raw_probs)

        elif method == DevigMethod.SHIN:
            if overround <= 1.0:
                probs = [q / overround for q in raw_probs]
                return cls._build_result(method, probs, overround, raw_probs, z=0.0)

            # Bisection root finder for Shin z in [0.0, 0.999999]
            def shin_obj(z: float) -> float:
                if z >= 1.0:
                    return -1.0
                total = 0.0
                for q in raw_probs:
                    disc = z * z + 4.0 * (1.0 - z) * q
                    if disc < 0:
                        disc = 0.0
                    p_i = ((math.sqrt(disc) - z) / (2.0 * (1.0 - z))) ** 2
                    total += p_i
                return total - 1.0

            low, high = 0.0, 0.999999
            for _ in range(60):
                mid = (low + high) / 2.0
                val = shin_obj(mid)
                if abs(val) < 1e-11:
                    break
                if val > 0:
                    low = mid
                else:
                    high = mid
            z_opt = (low + high) / 2.0

            probs = []
            for q in raw_probs:
                disc = max(0.0, z_opt * z_opt + 4.0 * (1.0 - z_opt) * q)
                p_i = ((math.sqrt(disc) - z_opt) / (2.0 * (1.0 - z_opt))) ** 2
                probs.append(p_i)
            # Normalize for machine precision
            s = sum(probs)
            probs = [p / s for p in probs]
            return cls._build_result(method, probs, overround, raw_probs, z=round(z_opt, 6))

        raise ValueError(f"Unsupported devig method: {method}")

    @classmethod
    def _build_result(
        cls,
        method: DevigMethod,
        probs: List[float],
        overround: float,
        raw_probs: List[float],
        z: Optional[float] = None
    ) -> DevigResult:
        s = sum(probs)
        probs = [p / s for p in probs]
        dec_odds = [round(1.0 / p, 4) for p in probs]
        ame_odds = [cls.decimal_to_american(d) for d in dec_odds]
        return DevigResult(
            method=method,
            fair_implied_probabilities=[round(p, 6) for p in probs],
            fair_decimal_odds=dec_odds,
            fair_american_odds=ame_odds,
            overround=round(overround, 6),
            raw_probabilities=[round(q, 6) for q in raw_probs],
            z_parameter=z
        )


# ==============================================================================
# 4. STATISTICAL DISTRIBUTION ENGINE (F11, F12, F13)
# ==============================================================================

class DistributionEngine:
    DEFAULT_CVS = {
        "QB": 0.28,
        "RB": 0.42,
        "WR": 0.55,
        "TE": 0.58,
        "PASS_YDS": 0.28,
        "RUSH_YDS": 0.42,
        "REC_YDS": 0.55
    }

    DEFAULT_ALPHAS = {
        "ANYTIME_TD": 0.22,
        "PASS_TDS": 0.12,
        "RECEPTIONS": 0.10,
        "PASS_INTS": 0.08
    }

    @classmethod
    def evaluate_continuous_prop(
        cls,
        projection_mean: float,
        line: float,
        position: str = "WR",
        stat_category: str = "rec_yds",
        dist_type: DistributionType = DistributionType.LOG_NORMAL,
        cv_override: Optional[float] = None
    ) -> DistributionResult:
        if projection_mean <= 0:
            raise ValueError(f"Projection mean must be positive, got {projection_mean}")
        if line < 0:
            raise ValueError(f"Line cannot be negative, got {line}")

        cv = cv_override or cls.DEFAULT_CVS.get(position.upper(), cls.DEFAULT_CVS.get(stat_category.upper(), 0.50))
        is_integer = float(line).is_integer()

        if dist_type == DistributionType.LOG_NORMAL:
            sigma_ln = math.sqrt(math.log(1.0 + cv * cv))
            mu_ln = math.log(projection_mean) - 0.5 * sigma_ln * sigma_ln
            dist = NormalDist(mu=mu_ln, sigma=sigma_ln)

            if line == 0.0:
                p_over = 1.0
                p_under = 0.0
                p_push = 0.0
            elif is_integer:
                p_push = dist.cdf(math.log(line + 0.5)) - dist.cdf(math.log(max(1e-4, line - 0.5)))
                p_over = 1.0 - dist.cdf(math.log(line + 0.5))
                p_under = dist.cdf(math.log(max(1e-4, line - 0.5)))
            else:
                p_push = 0.0
                p_over = 1.0 - dist.cdf(math.log(line))
                p_under = dist.cdf(math.log(line))

        elif dist_type == DistributionType.CALIBRATED_NORMAL:
            sigma = projection_mean * cv
            dist = NormalDist(mu=projection_mean, sigma=sigma)

            if is_integer:
                p_push = dist.cdf(line + 0.5) - dist.cdf(line - 0.5)
                p_over = 1.0 - dist.cdf(line + 0.5)
                p_under = dist.cdf(line - 0.5)
            else:
                p_push = 0.0
                p_over = 1.0 - dist.cdf(line)
                p_under = dist.cdf(line)

        else:
            raise ValueError(f"Unsupported continuous distribution: {dist_type}")

        # Normalization guard
        p_push = max(0.0, min(1.0, p_push))
        p_over = max(0.0, min(1.0, p_over))
        p_under = max(0.0, min(1.0, p_under))
        total = p_over + p_under + p_push
        if total > 0:
            p_over /= total
            p_under /= total
            p_push /= total

        no_push = max(1e-6, 1.0 - p_push)
        cond_over = p_over / no_push
        cond_under = p_under / no_push

        dec_over = round(1.0 / max(1e-6, cond_over), 4)
        dec_under = round(1.0 / max(1e-6, cond_under), 4)

        return DistributionResult(
            prob_over=round(p_over, 6),
            prob_under=round(p_under, 6),
            prob_push=round(p_push, 6),
            conditional_prob_over=round(cond_over, 6),
            conditional_prob_under=round(cond_under, 6),
            fair_decimal_over=dec_over,
            fair_decimal_under=dec_under,
            distribution_type=dist_type
        )

    @classmethod
    def evaluate_discrete_prop(
        cls,
        projection_mean: float,
        line: float,
        stat_category: str = "anytime_td",
        dist_type: DistributionType = DistributionType.NEGATIVE_BINOMIAL,
        alpha_override: Optional[float] = None
    ) -> DistributionResult:
        if projection_mean <= 0:
            return DistributionResult(
                prob_over=0.0,
                prob_under=1.0,
                prob_push=0.0,
                conditional_prob_over=0.0,
                conditional_prob_under=1.0,
                fair_decimal_over=999.0,
                fair_decimal_under=1.0,
                distribution_type=dist_type
            )

        alpha = alpha_override or cls.DEFAULT_ALPHAS.get(stat_category.upper(), 0.15)
        is_integer = float(line).is_integer()

        def poisson_pmf(k: int, lam: float) -> float:
            return math.exp(k * math.log(lam) - lam - math.lgamma(k + 1))

        def negbin_pmf(k: int, mu: float, a: float) -> float:
            r = 1.0 / a
            p_nb = 1.0 / (1.0 + a * mu)
            log_pmf = (
                math.lgamma(k + r) - math.lgamma(r) - math.lgamma(k + 1)
                + r * math.log(p_nb) + k * math.log(1.0 - p_nb)
            )
            return math.exp(log_pmf)

        pmf_func = (lambda k: poisson_pmf(k, projection_mean)) if dist_type == DistributionType.POISSON else (lambda k: negbin_pmf(k, projection_mean, alpha))

        if is_integer:
            L = int(line)
            p_push = pmf_func(L)
            p_under = sum(pmf_func(k) for k in range(L))
            p_over = max(0.0, 1.0 - (p_under + p_push))
        else:
            L_floor = int(math.floor(line))
            p_push = 0.0
            p_under = sum(pmf_func(k) for k in range(L_floor + 1))
            p_over = max(0.0, 1.0 - p_under)

        total = p_over + p_under + p_push
        if total > 0:
            p_over /= total
            p_under /= total
            p_push /= total

        no_push = max(1e-6, 1.0 - p_push)
        cond_over = p_over / no_push
        cond_under = p_under / no_push

        dec_over = round(1.0 / max(1e-6, cond_over), 4)
        dec_under = round(1.0 / max(1e-6, cond_under), 4)

        return DistributionResult(
            prob_over=round(p_over, 6),
            prob_under=round(p_under, 6),
            prob_push=round(p_push, 6),
            conditional_prob_over=round(cond_over, 6),
            conditional_prob_under=round(cond_under, 6),
            fair_decimal_over=dec_over,
            fair_decimal_under=dec_under,
            distribution_type=dist_type
        )


# ==============================================================================
# 5. DUAL-EDGE EV ENGINE & FRACTIONAL KELLY SIZING (F14, F15)
# ==============================================================================

class EVEngine:
    @staticmethod
    def calculate_ev(
        bet365_decimal: float,
        market_fair_prob: Optional[float],
        model_fair_prob: Optional[float],
        prob_push: float = 0.0,
        weight_market: float = 0.60,
        weight_model: float = 0.40,
        bankroll: float = 2000.0,
        kelly_fraction: float = 0.25,
        min_stake: float = 5.0,
        max_bankroll_pct: float = 0.05
    ) -> EVResult:
        if bet365_decimal <= 1.0:
            raise ValueError(f"Bet365 decimal odds must be > 1.0, got {bet365_decimal}")

        mkt_ev = None
        if market_fair_prob is not None:
            mkt_ev = (market_fair_prob * bet365_decimal) - (1.0 - prob_push)

        mdl_ev = None
        if model_fair_prob is not None:
            mdl_ev = (model_fair_prob * bet365_decimal) - (1.0 - prob_push)

        # Blended Probability
        if market_fair_prob is not None and model_fair_prob is not None:
            total_w = weight_market + weight_model
            w_mkt = weight_market / total_w
            w_mdl = weight_model / total_w
            blend_prob = (w_mkt * market_fair_prob) + (w_mdl * model_fair_prob)
        elif market_fair_prob is not None:
            blend_prob = market_fair_prob
        elif model_fair_prob is not None:
            blend_prob = model_fair_prob
        else:
            blend_prob = 0.0

        blended_ev = (blend_prob * bet365_decimal) - (1.0 - prob_push)

        # Kelly Sizing
        if blended_ev <= 0 or bankroll <= 0:
            full_f = 0.0
            quarter_f = 0.0
            q_stake = 0.0
            h_stake = 0.0
            f_stake = 0.0
            rec_stake = 0.0
            is_capped = False
        else:
            b_odds = bet365_decimal - 1.0
            full_f = max(0.0, blended_ev / max(1e-4, b_odds))
            quarter_f = full_f * kelly_fraction
            
            raw_q_stake = bankroll * quarter_f
            raw_h_stake = bankroll * (full_f * 0.50)
            raw_f_stake = bankroll * full_f

            # Enforce risk caps (max 5% bankroll or $250 max)
            cap_limit = min(bankroll * max_bankroll_pct, 250.0)
            
            is_capped = raw_q_stake > cap_limit
            
            if raw_q_stake < min_stake:
                rec_stake = 0.0
            else:
                rec_stake = round(min(raw_q_stake, cap_limit), 2)

            q_stake = round(min(raw_q_stake, cap_limit), 2)
            h_stake = round(min(raw_h_stake, cap_limit), 2)
            f_stake = round(min(raw_f_stake, cap_limit), 2)

        return EVResult(
            market_implied_ev=round(mkt_ev * 100.0, 2) if mkt_ev is not None else None,
            model_implied_ev=round(mdl_ev * 100.0, 2) if mdl_ev is not None else None,
            blended_ev=round(blended_ev * 100.0, 2),
            blended_win_prob=round(blend_prob, 4),
            quarter_kelly_fraction=round(quarter_f, 6),
            quarter_kelly_stake=q_stake,
            half_kelly_stake=h_stake,
            full_kelly_stake=f_stake,
            recommended_stake=rec_stake,
            is_capped=is_capped
        )


# ==============================================================================
# 6. INGESTION PARSERS & MOCK ADAPTERS (F05, F10)
# ==============================================================================

class FantasyPointsIngestionEngine:
    @staticmethod
    def sanitize_float(val: Any, default: float = 0.0) -> float:
        if val is None:
            return default
        s = str(val).strip()
        if not s or s in ("--", "N/A", "null", "None", "*", "-", "OUT", "IR"):
            return default
        # Strip annotations e.g. "24.5 (Q)" or "1,250"
        s = re.sub(r"\s*\(.*?\)", "", s)
        s = s.replace(",", "").replace("*", "").strip()
        try:
            return float(s)
        except ValueError:
            return default

    @classmethod
    def parse_csv_text(cls, text: str) -> List[PlayerProjection]:
        if not text or not text.strip():
            return []
        
        # Delimiter detection
        first_line = text.strip().split("\n")[0]
        delim = "\t" if "\t" in first_line else ("," if "," in first_line else "|")
        
        reader = csv.DictReader(text.strip().splitlines(), delimiter=delim)
        projections = []

        for row in reader:
            # Header synonym normalization
            clean_row = {}
            for k, v in row.items():
                if not k:
                    continue
                k_clean = k.strip().lower().replace(" ", "_").replace(".", "")
                clean_row[k_clean] = v

            raw_name = clean_row.get("player") or clean_row.get("name") or clean_row.get("player_name") or ""
            if not raw_name:
                continue

            clean_name, suffix = PlayerNameNormalizer.clean_name(raw_name)
            raw_team = clean_row.get("team") or clean_row.get("tm") or ""
            team = TeamNormalizer.canonical_team(raw_team)
            
            raw_pos = clean_row.get("pos") or clean_row.get("position") or ""
            pos_str = raw_pos.strip().upper()
            
            # Position inference if missing
            pass_att = cls.sanitize_float(clean_row.get("pass_att") or clean_row.get("patt"))
            rush_att = cls.sanitize_float(clean_row.get("rush_att") or clean_row.get("ratt"))
            rec = cls.sanitize_float(clean_row.get("rec") or clean_row.get("receptions"))
            
            if not pos_str:
                if pass_att > 10.0:
                    pos_str = "QB"
                elif rush_att > 5.0:
                    pos_str = "RB"
                elif rec > 2.0:
                    pos_str = "WR"
                else:
                    pos_str = "WR"
            
            try:
                position = PlayerPosition(pos_str)
            except ValueError:
                position = PlayerPosition.WR

            proj = PlayerProjection(
                player_id=f"nfl_{clean_name}_{team.lower()}",
                raw_name=raw_name,
                normalized_name=clean_name,
                team=team,
                position=position,
                opponent=TeamNormalizer.canonical_team(clean_row.get("opp") or clean_row.get("opponent") or ""),
                pass_att=pass_att,
                pass_cmp=cls.sanitize_float(clean_row.get("pass_cmp") or clean_row.get("pcmp")),
                pass_yds=cls.sanitize_float(clean_row.get("pass_yds") or clean_row.get("pyds")),
                pass_td=cls.sanitize_float(clean_row.get("pass_td") or clean_row.get("ptd")),
                pass_int=cls.sanitize_float(clean_row.get("pass_int") or clean_row.get("pint")),
                rush_att=rush_att,
                rush_yds=cls.sanitize_float(clean_row.get("rush_yds") or clean_row.get("ryds")),
                rush_td=cls.sanitize_float(clean_row.get("rush_td") or clean_row.get("rtd")),
                targets=cls.sanitize_float(clean_row.get("targets") or clean_row.get("tgt")),
                receptions=rec,
                rec_yds=cls.sanitize_float(clean_row.get("rec_yds") or clean_row.get("reyds")),
                rec_td=cls.sanitize_float(clean_row.get("rec_td") or clean_row.get("rectd")),
                anytime_td_mean=cls.sanitize_float(clean_row.get("anytime_td") or clean_row.get("anytime_td_mean")),
                fantasy_points=cls.sanitize_float(clean_row.get("fantasy_points") or clean_row.get("fpts"))
            )
            projections.append(proj)

        return projections


class MockTheOddsApiAdapter:
    @staticmethod
    def parse_payload(payload: Union[str, List[Dict[str, Any]]]) -> List[MarketOffer]:
        if isinstance(payload, str):
            if not payload.strip():
                return []
            data = json.loads(payload)
        else:
            data = payload

        offers = []
        for event in data:
            event_id = event.get("id", "")
            for book in event.get("bookmakers", []):
                book_key = book.get("key", "").lower()
                for mkt in book.get("markets", []):
                    try:
                        mkt_type = MarketType.from_string(mkt.get("key", ""))
                    except ValueError:
                        continue

                    for out in mkt.get("outcomes", []):
                        side = out.get("name", "")
                        player = out.get("description")
                        point = float(out.get("point", 0.0))
                        price = float(out.get("price", 1.909))
                        
                        odds = OddsValue.from_decimal(price)
                        offer = MarketOffer(
                            offer_id=f"{event_id}_{book_key}_{mkt_type.value}_{player or side}_{point}",
                            event_id=event_id,
                            bookmaker=book_key,
                            market_type=mkt_type,
                            player_name=player,
                            side=side,
                            point=point,
                            odds=odds,
                            timestamp=book.get("last_update", "")
                        )
                        offers.append(offer)
        return offers


class MockCsvOddsAdapter:
    @staticmethod
    def parse_csv(csv_text: str) -> List[MarketOffer]:
        if not csv_text or not csv_text.strip():
            return []
        reader = csv.DictReader(csv_text.strip().splitlines())
        offers = []
        for i, row in enumerate(reader):
            mkt_str = row.get("Market") or row.get("market") or ""
            try:
                mkt_type = MarketType.from_string(mkt_str)
            except ValueError:
                continue

            book = row.get("Bookmaker") or row.get("bookmaker") or "bet365"
            player = row.get("Player") or row.get("player")
            side = row.get("Option") or row.get("side") or "Over"
            line = float(row.get("Line") or row.get("line") or 0.0)
            
            p_ame = row.get("Price_American") or row.get("american")
            p_dec = row.get("Price_Decimal") or row.get("decimal")
            if p_ame:
                odds = OddsValue.from_american(int(p_ame))
            elif p_dec:
                odds = OddsValue.from_decimal(float(p_dec))
            else:
                odds = OddsValue.from_american(-110)

            offer = MarketOffer(
                offer_id=f"csv_offer_{i}_{book}_{mkt_type.value}",
                event_id=row.get("Event") or "event_1",
                bookmaker=book.lower(),
                market_type=mkt_type,
                player_name=player,
                side=side,
                point=line,
                odds=odds
            )
            offers.append(offer)
        return offers


# ==============================================================================
# 7. IN-MEMORY CACHE & FASTAPI CLIENT (F16, F17, F18, F19, F20)
# ==============================================================================

class InMemoryCache:
    def __init__(self):
        self._lock = asyncio.Lock()
        self.odds: List[MarketOffer] = []
        self.projections: List[PlayerProjection] = []
        self.opportunities: List[MatchedEVOpportunity] = []
        self.bankroll: float = 2000.0
        self.kelly_fraction: float = 0.25
        self.min_ev: float = 0.0
        self.last_recalculation: str = ""

    async def update_odds(self, offers: List[MarketOffer]) -> None:
        async with self._lock:
            self.odds = list(offers)

    async def update_projections(self, projections: List[PlayerProjection]) -> None:
        async with self._lock:
            self.projections = list(projections)

    async def recalculate(self) -> None:
        async with self._lock:
            self._execute_recalc_sync()

    def _execute_recalc_sync(self) -> None:
        opps = []
        proj_map = {p.normalized_name: p for p in self.projections}

        # Index Bet365 offers
        bet365_offers = [o for o in self.odds if "bet365" in o.bookmaker.lower()]
        sharp_offers = [o for o in self.odds if any(k in o.bookmaker.lower() for k in ("pinnacle", "circa"))]

        for b_off in bet365_offers:
            if not b_off.player_name:
                continue

            c_name, _ = PlayerNameNormalizer.clean_name(b_off.player_name)
            proj = proj_map.get(c_name)

            # Match sharp benchmark
            sharp_match = None
            for s_off in sharp_offers:
                if s_off.market_type == b_off.market_type and s_off.side == b_off.side and math.isclose(s_off.point, b_off.point, abs_tol=0.01):
                    if s_off.player_name:
                        s_cname, _ = PlayerNameNormalizer.clean_name(s_off.player_name)
                        if s_cname == c_name:
                            sharp_match = s_off
                            break

            market_fair_prob = None
            prob_push = 0.0
            if sharp_match:
                # Find opposing sharp side
                opp_side = "Under" if sharp_match.side.lower() == "over" else "Over"
                sharp_opp = next((o for o in sharp_offers if o.market_type == sharp_match.market_type and o.side.lower() == opp_side.lower() and math.isclose(o.point, sharp_match.point, abs_tol=0.01)), None)
                if sharp_opp:
                    devig_res = DevigEngine.devig([sharp_match.odds.decimal, sharp_opp.odds.decimal], DevigMethod.SHIN)
                    market_fair_prob = devig_res.fair_implied_probabilities[0]

            model_fair_prob = None
            if proj:
                stat_mean = 0.0
                if b_off.market_type == MarketType.PASSING_YARDS:
                    stat_mean = proj.pass_yds
                    dist_res = DistributionEngine.evaluate_continuous_prop(stat_mean, b_off.point, proj.position.value, "pass_yds", DistributionType.CALIBRATED_NORMAL)
                elif b_off.market_type == MarketType.RUSHING_YARDS:
                    stat_mean = proj.rush_yds
                    dist_res = DistributionEngine.evaluate_continuous_prop(stat_mean, b_off.point, proj.position.value, "rush_yds", DistributionType.LOG_NORMAL)
                elif b_off.market_type == MarketType.RECEIVING_YARDS:
                    stat_mean = proj.rec_yds
                    dist_res = DistributionEngine.evaluate_continuous_prop(stat_mean, b_off.point, proj.position.value, "rec_yds", DistributionType.LOG_NORMAL)
                elif b_off.market_type == MarketType.RECEPTIONS:
                    stat_mean = proj.receptions
                    dist_res = DistributionEngine.evaluate_discrete_prop(stat_mean, b_off.point, "receptions", DistributionType.NEGATIVE_BINOMIAL)
                elif b_off.market_type == MarketType.PASSING_TDS:
                    stat_mean = proj.pass_td
                    dist_res = DistributionEngine.evaluate_discrete_prop(stat_mean, b_off.point, "pass_tds", DistributionType.NEGATIVE_BINOMIAL)
                elif b_off.market_type == MarketType.ANYTIME_TD:
                    stat_mean = proj.anytime_td_mean
                    dist_res = DistributionEngine.evaluate_discrete_prop(stat_mean, 0.5, "anytime_td", DistributionType.POISSON)
                else:
                    dist_res = None

                if dist_res:
                    prob_push = dist_res.prob_push
                    model_fair_prob = dist_res.prob_over if b_off.side.lower() in ("over", "yes") else dist_res.prob_under

            ev_res = EVEngine.calculate_ev(
                bet365_decimal=b_off.odds.decimal,
                market_fair_prob=market_fair_prob,
                model_fair_prob=model_fair_prob,
                prob_push=prob_push,
                bankroll=self.bankroll,
                kelly_fraction=self.kelly_fraction
            )

            opp = MatchedEVOpportunity(
                opportunity_id=f"opp_{b_off.offer_id}",
                player_name=b_off.player_name,
                team=proj.team if proj else "UNK",
                opponent=proj.opponent if proj else "UNK",
                market_type=b_off.market_type,
                side=b_off.side,
                line=b_off.point,
                bet365_decimal=b_off.odds.decimal,
                bet365_american=b_off.odds.american,
                sharp_benchmark_book=sharp_match.bookmaker if sharp_match else "None",
                sharp_fair_decimal=round(1.0 / market_fair_prob, 2) if market_fair_prob else None,
                model_fair_prob=model_fair_prob,
                market_ev_percent=ev_res.market_implied_ev,
                model_ev_percent=ev_res.model_implied_ev,
                blended_ev_percent=ev_res.blended_ev,
                quarter_kelly_stake=ev_res.quarter_kelly_stake,
                recommended_stake=ev_res.recommended_stake,
                prob_push=prob_push
            )
            opps.append(opp)

        self.opportunities = opps
        self.last_recalculation = "2026-08-15T01:00:00Z"

    async def get_opportunities(
        self,
        market_type: Optional[str] = None,
        min_ev: float = 0.0,
        search: Optional[str] = None,
        sort_by: str = "blended_ev",
        sort_desc: bool = True
    ) -> List[MatchedEVOpportunity]:
        async with self._lock:
            res = list(self.opportunities)

            if market_type:
                res = [o for o in res if o.market_type.value == market_type or o.market_type.name.lower() == market_type.lower()]

            if min_ev > 0.0:
                res = [o for o in res if o.blended_ev_percent >= min_ev]

            if search:
                s_lower = search.lower().strip()
                res = [o for o in res if s_lower in o.player_name.lower() or s_lower in o.team.lower()]

            # Sorting
            def sort_key(item: MatchedEVOpportunity):
                if sort_by in ("blended_ev", "ev"):
                    return item.blended_ev_percent
                elif sort_by in ("stake", "kelly"):
                    return item.recommended_stake
                elif sort_by == "player_name":
                    return item.player_name
                return item.blended_ev_percent

            res.sort(key=sort_key, reverse=sort_desc)
            return res


class MockFastAPIClient:
    def __init__(self, cache: Optional[InMemoryCache] = None):
        self.cache = cache or InMemoryCache()

    async def get(self, path: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        params = params or {}
        if path == "/health" or path == "/api/v1/health" or path == "/meta/health":
            return {"status_code": 200, "json": {"status": "healthy", "service": "nfl-ev-engine"}}
        
        if path.startswith("/api/v1/opportunities") or path.startswith("/opportunities"):
            if "/breakdown" in path:
                # Modal Prop Breakdown
                opp_id = path.split("/")[-2] if path.endswith("/breakdown") else path.split("/")[-1]
                opp = next((o for o in self.cache.opportunities if o.opportunity_id == opp_id or opp_id in o.opportunity_id), None)
                if not opp:
                    opp = self.cache.opportunities[0] if self.cache.opportunities else None
                return {
                    "status_code": 200,
                    "json": {
                        "opportunity": opp.__dict__ if opp else {},
                        "math_trace": {
                            "formula": "EV = (p * Decimal) - (1 - p_push)",
                            "shin_z": 0.1245,
                            "distribution": "log_normal",
                            "chart_points": [{"x": 50, "y": 0.01}, {"x": 65, "y": 0.03}]
                        }
                    }
                }
            
            mkt = params.get("market") or params.get("market_type")
            min_ev = float(params.get("min_ev", 0.0))
            search = params.get("search")
            sort_by = params.get("sort_by", "blended_ev")
            sort_desc = params.get("sort_order", "desc").lower() == "desc"
            
            opps = await self.cache.get_opportunities(
                market_type=mkt,
                min_ev=min_ev,
                search=search,
                sort_by=sort_by,
                sort_desc=sort_desc
            )
            return {"status_code": 200, "json": {"count": len(opps), "items": [o.__dict__ for o in opps]}}

        if path == "/api/v1/settings" or path == "/config/bankroll":
            return {
                "status_code": 200,
                "json": {
                    "bankroll": self.cache.bankroll,
                    "kelly_fraction": self.cache.kelly_fraction,
                    "min_stake": 5.0,
                    "max_bankroll_pct": 0.05
                }
            }

        if path.endswith("/export/csv") or path == "/api/v1/export/csv":
            opps = self.cache.opportunities
            csv_lines = ["Player,Team,Market,Line,Side,Bet365_Decimal,EV_Percent,Stake"]
            for o in opps:
                csv_lines.append(f"{o.player_name},{o.team},{o.market_type.value},{o.line},{o.side},{o.bet365_decimal},{o.blended_ev_percent},{o.recommended_stake}")
            return {"status_code": 200, "text": "\n".join(csv_lines)}

        return {"status_code": 404, "json": {"detail": f"Path not found: {path}"}}

    async def post(self, path: str, json_body: Optional[Any] = None, data: Optional[Any] = None) -> Dict[str, Any]:
        if path.startswith("/api/v1/upload/projections") or path == "/ingest/projections/upload":
            raw_text = data if isinstance(data, str) else (json_body.get("csv_text", "") if isinstance(json_body, dict) else "")
            projections = FantasyPointsIngestionEngine.parse_csv_text(raw_text)
            await self.cache.update_projections(projections)
            await self.cache.recalculate()
            return {"status_code": 200, "json": {"status": "success", "imported_count": len(projections)}}

        if path.startswith("/api/v1/upload/odds") or path == "/ingest/odds/upload":
            if isinstance(json_body, list) or (isinstance(json_body, dict) and "bookmakers" in str(json_body)):
                offers = MockTheOddsApiAdapter.parse_payload(json_body)
            elif isinstance(data, str):
                offers = MockCsvOddsAdapter.parse_csv(data)
            else:
                offers = []
            await self.cache.update_odds(offers)
            await self.cache.recalculate()
            return {"status_code": 200, "json": {"status": "success", "offers_updated": len(offers)}}

        if path == "/api/v1/recalculate" or path == "/recalculate":
            await self.cache.recalculate()
            return {"status_code": 200, "json": {"status": "success", "opportunities_count": len(self.cache.opportunities)}}

        return {"status_code": 404, "json": {"detail": f"Path not found: {path}"}}

    async def put(self, path: str, json_body: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        json_body = json_body or {}
        if path == "/config/bankroll" or path == "/api/v1/settings":
            if "bankroll" in json_body:
                self.cache.bankroll = float(json_body["bankroll"])
            if "kelly_fraction" in json_body:
                self.cache.kelly_fraction = float(json_body["kelly_fraction"])
            await self.cache.recalculate()
            return {"status_code": 200, "json": {"status": "success", "bankroll": self.cache.bankroll, "kelly_fraction": self.cache.kelly_fraction}}
        return {"status_code": 404, "json": {"detail": f"Path not found: {path}"}}
