"""
app.core.distributions: High-performance statistical probability engine for NFL player props.

Supports:
- Continuous yardage distributions (Log-Normal, Calibrated Normal) with empirical positional CVs.
- Discrete count distributions (Poisson, Negative Binomial) with empirical overdispersion alphas.
- Continuity corrections on whole-number lines vs half-point lines.
- Exact calculation of P(Over), P(Under), P(Push), conditional win probabilities, and fair decimal odds.
- PDF and PMF coordinate generator for Chart.js interactive visualization.
"""
from __future__ import annotations

import math
from enum import Enum
from statistics import NormalDist
from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.projections import Position, StatCategory


class DistributionType(str, Enum):
    """Supported statistical probability distribution models."""
    LOG_NORMAL = "log_normal"
    CALIBRATED_NORMAL = "calibrated_normal"
    POISSON = "poisson"
    NEGATIVE_BINOMIAL = "negative_binomial"


class DistributionResult(BaseModel):
    """
    Type-safe result container for statistical player prop probability evaluations.
    """
    model_config = ConfigDict(populate_by_name=True, from_attributes=True)

    prob_over: float = Field(..., description="Unconditional probability of exceeding line: P(Y > L)")
    prob_under: float = Field(..., description="Unconditional probability of falling below line: P(Y < L)")
    prob_push: float = Field(default=0.0, description="Probability of exact landing on integer line: P(Y = L)")
    conditional_prob_over: float = Field(..., description="Conditional win probability: P(Over | No Push)")
    conditional_prob_under: float = Field(..., description="Conditional win probability: P(Under | No Push)")
    fair_decimal_over: float = Field(..., description="Fair decimal odds for Over: 1 / P(Over | No Push)")
    fair_decimal_under: float = Field(..., description="Fair decimal odds for Under: 1 / P(Under | No Push)")
    distribution_type: DistributionType = Field(..., description="Parametric distribution model applied")


class DistributionEngine:
    """
    Core statistical probability engine for player prop line evaluations.
    """

    # Empirical NFL Coefficient of Variation (CV = sigma / mean) defaults
    DEFAULT_POSITIONAL_CV: dict[str, float] = {
        "QB": 0.28,
        "RB": 0.42,
        "WR": 0.55,
        "TE": 0.52,
        "K": 0.40,
        "DEF": 0.50,
        "DST": 0.50,
        "FLEX": 0.50,
    }

    DEFAULT_STAT_CATEGORY_CV: dict[str, float] = {
        "passing_yards": 0.28,
        "pass_yds": 0.28,
        "player_pass_yds": 0.28,
        "rushing_yards": 0.42,
        "rush_yds": 0.42,
        "player_rush_yds": 0.42,
        "receiving_yards": 0.55,
        "rec_yds": 0.55,
        "player_rec_yds": 0.55,
        "player_reception_yds": 0.55,
    }

    # Empirical NFL Overdispersion parameter (alpha) defaults for Negative Binomial
    DEFAULT_STAT_CATEGORY_ALPHA: dict[str, float] = {
        "anytime_td": 0.22,
        "player_anytime_td": 0.22,
        "td": 0.22,
        "passing_tds": 0.12,
        "pass_tds": 0.12,
        "player_pass_tds": 0.12,
        "pass_td": 0.12,
        "receptions": 0.10,
        "player_receptions": 0.10,
        "rec": 0.10,
        "passing_interceptions": 0.08,
        "pass_ints": 0.08,
        "player_pass_interceptions": 0.08,
        "interceptions": 0.08,
        "int": 0.08,
        "rushing_tds": 0.15,
        "rush_tds": 0.15,
        "receiving_tds": 0.15,
        "rec_tds": 0.15,
        "sacks": 0.15,
        "field_goals": 0.15,
    }

    @classmethod
    def get_default_cv(
        cls,
        position: Optional[Union[str, Position]] = None,
        stat_category: Optional[Union[str, StatCategory]] = None,
    ) -> float:
        """Resolve empirical default CV from position or stat category."""
        if position:
            pos_key = position.value.upper() if isinstance(position, Position) else str(position).upper().strip()
            if pos_key in cls.DEFAULT_POSITIONAL_CV:
                return cls.DEFAULT_POSITIONAL_CV[pos_key]

        if stat_category:
            cat_key = stat_category.value.lower() if isinstance(stat_category, StatCategory) else str(stat_category).lower().strip()
            if cat_key in cls.DEFAULT_STAT_CATEGORY_CV:
                return cls.DEFAULT_STAT_CATEGORY_CV[cat_key]

        return 0.50

    @classmethod
    def get_default_alpha(
        cls,
        stat_category: Optional[Union[str, StatCategory]] = None,
    ) -> float:
        """Resolve empirical default overdispersion alpha for count prop."""
        if stat_category:
            cat_key = stat_category.value.lower() if isinstance(stat_category, StatCategory) else str(stat_category).lower().strip()
            if cat_key in cls.DEFAULT_STAT_CATEGORY_ALPHA:
                return cls.DEFAULT_STAT_CATEGORY_ALPHA[cat_key]

        return 0.15

    @classmethod
    def evaluate_continuous_prop(
        cls,
        projection_mean: float,
        line: float,
        position: Union[str, Position] = "WR",
        stat_category: Union[str, StatCategory] = "rec_yds",
        dist_type: DistributionType = DistributionType.LOG_NORMAL,
        cv_override: Optional[float] = None,
    ) -> DistributionResult:
        """
        Evaluate continuous yardage prop over/under/push probabilities.
        """
        if projection_mean <= 0.0:
            raise ValueError(f"Projection mean must be positive, got {projection_mean}")
        if line < 0.0:
            raise ValueError(f"Line cannot be negative, got {line}")

        # Resolve CV
        cv = cv_override if (cv_override is not None and cv_override > 0.0) else cls.get_default_cv(position, stat_category)

        # Zero line special boundary
        if line == 0.0:
            return DistributionResult(
                prob_over=1.0,
                prob_under=0.0,
                prob_push=0.0,
                conditional_prob_over=1.0,
                conditional_prob_under=0.0,
                fair_decimal_over=1.0,
                fair_decimal_under=999.0,
                distribution_type=dist_type,
            )

        is_integer = float(line).is_integer()

        if dist_type == DistributionType.LOG_NORMAL:
            sigma_ln = math.sqrt(math.log(1.0 + cv * cv))
            mu_ln = math.log(projection_mean) - 0.5 * sigma_ln * sigma_ln
            dist = NormalDist(mu=mu_ln, sigma=sigma_ln)

            if is_integer:
                p_under = dist.cdf(math.log(max(1e-4, line - 0.5)))
                p_push = dist.cdf(math.log(line + 0.5)) - p_under
                p_over = 1.0 - dist.cdf(math.log(line + 0.5))
            else:
                p_under = dist.cdf(math.log(line))
                p_push = 0.0
                p_over = 1.0 - p_under

        elif dist_type == DistributionType.CALIBRATED_NORMAL:
            sigma = projection_mean * cv
            dist = NormalDist(mu=projection_mean, sigma=sigma)

            if is_integer:
                p_under = dist.cdf(line - 0.5)
                p_push = dist.cdf(line + 0.5) - p_under
                p_over = 1.0 - dist.cdf(line + 0.5)
            else:
                p_under = dist.cdf(line)
                p_push = 0.0
                p_over = 1.0 - p_under

        else:
            raise ValueError(f"Unsupported continuous distribution type: {dist_type}")

        return cls._build_result(p_over, p_under, p_push, dist_type)

    @classmethod
    def evaluate_discrete_prop(
        cls,
        projection_mean: float,
        line: float,
        stat_category: Union[str, StatCategory] = "anytime_td",
        dist_type: DistributionType = DistributionType.NEGATIVE_BINOMIAL,
        alpha_override: Optional[float] = None,
    ) -> DistributionResult:
        """
        Evaluate discrete count prop over/under/push probabilities.
        """
        if line < 0.0:
            raise ValueError(f"Line cannot be negative, got {line}")

        if projection_mean <= 0.0:
            return DistributionResult(
                prob_over=0.0,
                prob_under=1.0,
                prob_push=0.0,
                conditional_prob_over=0.0,
                conditional_prob_under=1.0,
                fair_decimal_over=999.0,
                fair_decimal_under=1.0,
                distribution_type=dist_type,
            )

        alpha = alpha_override if (alpha_override is not None and alpha_override > 0.0) else cls.get_default_alpha(stat_category)
        is_integer = float(line).is_integer()

        def poisson_pmf(k: int, lam: float) -> float:
            return math.exp(k * math.log(lam) - lam - math.lgamma(k + 1))

        def negbin_pmf(k: int, mu: float, a: float) -> float:
            if a <= 1e-6:
                return poisson_pmf(k, mu)
            r = 1.0 / a
            p_nb = 1.0 / (1.0 + a * mu)
            log_pmf = (
                math.lgamma(k + r) - math.lgamma(r) - math.lgamma(k + 1)
                + r * math.log(p_nb) + k * math.log(1.0 - p_nb)
            )
            return math.exp(log_pmf)

        pmf_func = (
            (lambda k: poisson_pmf(k, projection_mean))
            if dist_type == DistributionType.POISSON
            else (lambda k: negbin_pmf(k, projection_mean, alpha))
        )

        if is_integer:
            L_int = int(round(line))
            p_push = pmf_func(L_int)
            p_under = sum(pmf_func(k) for k in range(L_int))
            p_over = max(0.0, 1.0 - (p_under + p_push))
        else:
            L_floor = int(math.floor(line))
            p_push = 0.0
            p_under = sum(pmf_func(k) for k in range(L_floor + 1))
            p_over = max(0.0, 1.0 - p_under)

        return cls._build_result(p_over, p_under, p_push, dist_type)

    @classmethod
    def _build_result(
        cls,
        p_over: float,
        p_under: float,
        p_push: float,
        dist_type: DistributionType,
    ) -> DistributionResult:
        """Internal helper to normalize probabilities and compute conditional fair odds."""
        p_over = max(0.0, min(1.0, p_over))
        p_under = max(0.0, min(1.0, p_under))
        p_push = max(0.0, min(1.0, p_push))

        total = p_over + p_under + p_push
        if total > 0.0:
            p_over /= total
            p_under /= total
            p_push /= total

        no_push = max(1e-9, 1.0 - p_push)
        cond_over = p_over / no_push
        cond_under = p_under / no_push

        dec_over = round(1.0 / max(1e-6, cond_over), 4) if cond_over > 1e-4 else 999.0
        dec_under = round(1.0 / max(1e-6, cond_under), 4) if cond_under > 1e-4 else 999.0

        return DistributionResult(
            prob_over=round(p_over, 6),
            prob_under=round(p_under, 6),
            prob_push=round(p_push, 6),
            conditional_prob_over=round(cond_over, 6),
            conditional_prob_under=round(cond_under, 6),
            fair_decimal_over=dec_over,
            fair_decimal_under=dec_under,
            distribution_type=dist_type,
        )

    @classmethod
    def generate_density_curve(
        cls,
        projection_mean: float,
        line: float,
        position: Union[str, Position] = "WR",
        stat_category: Union[str, StatCategory] = "rec_yds",
        dist_type: Optional[DistributionType] = None,
        cv_override: Optional[float] = None,
        alpha_override: Optional[float] = None,
        points: int = 100,
    ) -> dict[str, Any]:
        """
        Generate coordinates for frontend Chart.js rendering in Prop Breakdown drawer.
        """
        is_cont = True
        if isinstance(stat_category, StatCategory):
            is_cont = stat_category.is_continuous
        elif str(stat_category).lower() in (
            "anytime_td", "player_anytime_td", "receptions", "player_receptions",
            "pass_tds", "passing_tds", "pass_ints", "passing_interceptions",
            "rushing_tds", "receiving_tds", "sacks", "field_goals",
        ):
            is_cont = False

        if is_cont:
            active_dist = dist_type or DistributionType.LOG_NORMAL
            cv = cv_override if (cv_override is not None and cv_override > 0.0) else cls.get_default_cv(position, stat_category)
            max_x = max(projection_mean * 2.5, line * 1.8, 10.0)
            step = max_x / max(10, points)
            x_vals = [round(i * step, 2) for i in range(1, points + 1)]

            if active_dist == DistributionType.LOG_NORMAL:
                sigma_ln = math.sqrt(math.log(1.0 + cv * cv))
                mu_ln = math.log(max(1e-4, projection_mean)) - 0.5 * sigma_ln * sigma_ln
                y_vals = []
                for x in x_vals:
                    if x <= 0:
                        y_vals.append(0.0)
                    else:
                        pdf = (1.0 / (x * sigma_ln * math.sqrt(2 * math.pi))) * math.exp(
                            -((math.log(x) - mu_ln) ** 2) / (2 * sigma_ln * sigma_ln)
                        )
                        y_vals.append(round(pdf, 6))
            else:
                sigma = projection_mean * cv
                y_vals = [
                    round(
                        (1.0 / (sigma * math.sqrt(2 * math.pi)))
                        * math.exp(-((x - projection_mean) ** 2) / (2 * sigma * sigma)),
                        6,
                    )
                    for x in x_vals
                ]

            return {
                "type": "continuous",
                "x": x_vals,
                "y": y_vals,
                "line": line,
                "mean": projection_mean,
                "distribution": active_dist.value,
            }
        else:
            active_dist = dist_type or DistributionType.NEGATIVE_BINOMIAL
            alpha = alpha_override if (alpha_override is not None and alpha_override > 0.0) else cls.get_default_alpha(stat_category)
            max_k = max(10, int(projection_mean * 3) + 2)
            k_vals = list(range(max_k + 1))

            if active_dist == DistributionType.POISSON:
                y_vals = [
                    round(
                        math.exp(
                            k * math.log(max(1e-4, projection_mean))
                            - projection_mean
                            - math.lgamma(k + 1)
                        ),
                        6,
                    )
                    for k in k_vals
                ]
            else:
                r = 1.0 / max(1e-4, alpha)
                p_nb = 1.0 / (1.0 + alpha * projection_mean)
                y_vals = []
                for k in k_vals:
                    log_pmf = (
                        math.lgamma(k + r) - math.lgamma(r) - math.lgamma(k + 1)
                        + r * math.log(p_nb) + k * math.log(1.0 - p_nb)
                    )
                    y_vals.append(round(math.exp(log_pmf), 6))

            return {
                "type": "discrete",
                "x": k_vals,
                "y": y_vals,
                "line": line,
                "mean": projection_mean,
                "distribution": active_dist.value,
            }
