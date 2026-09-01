"""
app/core/devig.py

Quantitative Devigging & True Probability Engine.
Implements Multiplicative, Additive, Power, and Shin devigging algorithms
with pure Python Brent's method root-finding and optional SciPy fallback.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Sequence

# Optional SciPy import for external solver fallback/comparison if available
try:
    from scipy.optimize import brentq as _scipy_brentq  # type: ignore
    _HAS_SCIPY = True
except ImportError:
    _scipy_brentq = None
    _HAS_SCIPY = False


class DevigMethod(str, Enum):
    """Supported devigging algorithms."""
    MULTIPLICATIVE = "multiplicative"
    ADDITIVE = "additive"
    POWER = "power"
    SHIN = "shin"


@dataclass(frozen=True)
class DevigResult:
    """
    Immutable structured container representing the outcome of a devigging operation.
    Guarantees that fair implied probabilities sum strictly to 1.0 ± 0.0001.
    """
    fair_implied_probs: list[float]
    fair_decimal_odds: list[float]
    fair_american_odds: list[int]
    overround: float
    method: str
    extra_params: dict[str, Any] = field(default_factory=dict)
    raw_implied_probs: list[float] = field(default_factory=list)
    warning: str | None = None

    # Aliases and Ergonomic Properties
    @property
    def fair_implied_probabilities(self) -> list[float]:
        """Backwards compatibility alias for fair_implied_probs."""
        return self.fair_implied_probs

    @property
    def true_probs(self) -> list[float]:
        """Convenience alias for fair_implied_probs."""
        return self.fair_implied_probs

    @property
    def raw_probabilities(self) -> list[float]:
        """Backwards compatibility alias for raw_implied_probs."""
        return self.raw_implied_probs

    @property
    def z_parameter(self) -> float | None:
        """Shin informed trader parameter z if Shin method was used."""
        return self.extra_params.get("z")

    @property
    def k_parameter(self) -> float | None:
        """Power parameter k if Power method was used."""
        return self.extra_params.get("k")

    @property
    def overround_pct(self) -> float:
        """Total market overround percentage (e.g. 4.7619 for 1.047619)."""
        return round((self.overround - 1.0) * 100.0, 4)

    @property
    def margin_pct(self) -> float:
        """Theoretical bookmaker margin / hold percentage (e.g. 4.5455%)."""
        if self.overround <= 0:
            return 0.0
        return round(((self.overround - 1.0) / self.overround) * 100.0, 4)

    @property
    def vig_pct(self) -> float:
        """Alias for margin_pct."""
        return self.margin_pct

    @property
    def favorite_prob(self) -> float:
        """Maximum true win probability across outcomes."""
        return max(self.fair_implied_probs) if self.fair_implied_probs else 0.0

    @property
    def longshot_prob(self) -> float:
        """Minimum true win probability across outcomes."""
        return min(self.fair_implied_probs) if self.fair_implied_probs else 0.0

    def to_dict(self) -> dict[str, Any]:
        """Serialize result to a clean dictionary."""
        return {
            "method": self.method,
            "fair_implied_probs": self.fair_implied_probs,
            "fair_decimal_odds": self.fair_decimal_odds,
            "fair_american_odds": self.fair_american_odds,
            "overround": self.overround,
            "overround_pct": self.overround_pct,
            "margin_pct": self.margin_pct,
            "vig_pct": self.vig_pct,
            "warning": self.warning,
            "extra_params": self.extra_params,
            "raw_implied_probs": self.raw_implied_probs,
        }


# ==============================================================================
# Odds Conversion & Market Metrics
# ==============================================================================

def american_to_decimal(american_odds: int | float) -> float:
    """
    Convert American odds to Decimal odds.

    Formulas:
    - Positive odds (A >= +100): Decimal = 1.0 + (A / 100.0)
    - Negative odds (A <= -100): Decimal = 1.0 + (100.0 / |A|)
    - Even money (+100 or -100): Decimal = 2.0

    Raises:
        ValueError: If American odds fall strictly in (-100, 100) or are non-finite.
    """
    if not isinstance(american_odds, (int, float)) or math.isnan(american_odds) or math.isinf(american_odds):
        raise ValueError(f"Invalid American odds '{american_odds}'. Must be a finite number.")

    # Round to nearest integer representation if float
    a_int = int(round(american_odds))

    if -100 < a_int < 100:
        raise ValueError(
            f"Invalid American odds '{american_odds}'. American odds cannot be between -100 and +100."
        )

    if a_int >= 100:
        return round(1.0 + (a_int / 100.0), 6)
    else:
        return round(1.0 + (100.0 / abs(a_int)), 6)


def decimal_to_american(decimal_odds: float) -> int:
    """
    Convert Decimal odds to American integer odds.

    Formulas:
    - Decimal >= 2.0: American = round((Decimal - 1.0) * 100)
    - 1.0 < Decimal < 2.0: American = -round(100.0 / (Decimal - 1.0))

    Raises:
        ValueError: If Decimal odds <= 1.0 or are non-finite.
    """
    if not isinstance(decimal_odds, (int, float)) or math.isnan(decimal_odds) or math.isinf(decimal_odds) or decimal_odds <= 1.0:
        raise ValueError(
            f"Invalid Decimal odds '{decimal_odds}'. Decimal odds must be strictly greater than 1.0."
        )

    if decimal_odds >= 2.0:
        return int(round((decimal_odds - 1.0) * 100.0))
    else:
        denom = decimal_odds - 1.0
        if denom <= 0.0:
            raise ValueError(f"Invalid Decimal odds '{decimal_odds}'.")
        return -int(round(100.0 / denom))


def implied_probability(decimal_odds: float) -> float:
    """
    Calculate raw, un-devigged implied probability: q = 1 / Decimal.

    Raises:
        ValueError: If Decimal odds <= 1.0 or are non-finite.
    """
    if not isinstance(decimal_odds, (int, float)) or math.isnan(decimal_odds) or math.isinf(decimal_odds) or decimal_odds <= 1.0:
        raise ValueError(f"Decimal odds must be strictly > 1.0, got {decimal_odds}")
    return 1.0 / decimal_odds


def calculate_overround(decimal_odds_list: list[float] | Sequence[float]) -> float:
    """
    Calculate total bookmaker overround sum: S = sum(1 / D_i).

    Raises:
        ValueError: If market contains fewer than 2 outcomes or contains invalid odds.
    """
    if not decimal_odds_list or len(decimal_odds_list) < 2:
        raise ValueError(
            f"Market must have at least 2 outcomes, got {len(decimal_odds_list) if decimal_odds_list else 0}"
        )
    return sum(implied_probability(float(d)) for d in decimal_odds_list)


def odds_to_implied_probs(
    odds: list[float | int] | Sequence[float | int],
    odds_type: str = "decimal",
) -> list[float]:
    """
    Convert an arbitrary odds list into a list of raw implied probabilities [q_1, q_2, ...].
    """
    decimals = _normalize_odds_input(odds, odds_type)
    return [implied_probability(d) for d in decimals]


# ==============================================================================
# Pure Python Zero-Dependency Brent's Root Solver
# ==============================================================================

def _brentq(
    f: Callable[[float], float],
    a: float,
    b: float,
    xtol: float = 1e-12,
    rtol: float = 1e-12,
    maxiter: int = 100,
) -> tuple[float, int]:
    """
    Robust Pure Python implementation of Brent's method (brentq) for 1D root-finding.
    Combines root bracketing, secant method, and inverse quadratic interpolation.

    Returns:
        tuple[float, int]: (root, iteration_count)
    """
    fa = f(a)
    fb = f(b)

    if fa * fb > 0:
        raise ValueError(f"Root not bracketed: f({a})={fa}, f({b})={fb}")
    if abs(fa) < xtol:
        return a, 0
    if abs(fb) < xtol:
        return b, 0

    c = a
    fc = fa
    d = e = b - a
    iterations = 0

    for i in range(1, maxiter + 1):
        iterations = i
        if fb * fc > 0:
            c = a
            fc = fa
            d = e = b - a

        if abs(fc) < abs(fb):
            a = b
            b = c
            c = a
            fa = fb
            fb = fc
            fc = fa

        tol1 = 2.0 * 1e-16 * abs(b) + 0.5 * xtol
        xm = 0.5 * (c - b)

        if abs(xm) <= tol1 or abs(fb) < xtol:
            return b, iterations

        if abs(e) >= tol1 and abs(fa) > abs(fb):
            s = fb / fa
            if a == c:
                # Secant linear interpolation
                p = 2.0 * xm * s
                q = 1.0 - s
            else:
                # Inverse Quadratic Interpolation (IQI)
                q = fa / fc
                r = fb / fc
                p = s * (2.0 * xm * q * (q - r) - (b - a) * (r - 1.0))
                q = (q - 1.0) * (r - 1.0) * (s - 1.0)

            if p > 0:
                q = -q
            p = abs(p)

            # Accept interpolation step or fallback to bisection
            if 2.0 * p < min(3.0 * xm * q - abs(tol1 * q), abs(e * q)):
                e = d
                d = p / q
            else:
                d = xm
                e = d
        else:
            d = xm
            e = d

        a = b
        fa = fb
        if abs(d) > tol1:
            b += d
        else:
            b += tol1 if xm > 0 else -tol1
        fb = f(b)

    return b, iterations


def _normalize_odds_input(
    odds: list[float | int] | Sequence[float | int],
    odds_type: str,
) -> list[float]:
    """Helper to convert and validate input odds into a float list of decimal odds."""
    if odds is None or len(odds) < 2:
        raise ValueError(f"Market requires at least 2 outcomes, got {len(odds) if odds is not None else 0}")

    odds_type_lower = odds_type.lower().strip()
    if odds_type_lower == "american":
        decimals = [american_to_decimal(o) for o in odds]
    elif odds_type_lower == "decimal":
        decimals = []
        for o in odds:
            if not isinstance(o, (int, float)) or math.isnan(o) or math.isinf(o) or o <= 1.0:
                raise ValueError(f"Decimal odds must be strictly > 1.0, got {o}")
            decimals.append(float(o))
    else:
        raise ValueError(f"Unsupported odds_type '{odds_type}'. Use 'decimal' or 'american'.")

    return decimals


def _build_devig_result(
    probs: list[float],
    overround: float,
    method: str,
    raw_probs: list[float],
    extra_params: dict[str, Any] | None = None,
    warning: str | None = None,
) -> DevigResult:
    """Helper to build a complete DevigResult with guaranteed normalization sum = 1.0."""
    s = sum(probs)
    if s <= 0.0:
        raise ValueError("Sum of devigged probabilities must be strictly positive.")

    # High-precision normalization to ensure sum is strictly 1.00000000
    norm_probs = [p / s for p in probs]

    fair_decimals = [round(1.0 / p, 6) for p in norm_probs]
    fair_americans = [decimal_to_american(d) for d in fair_decimals]

    return DevigResult(
        fair_implied_probs=norm_probs,
        fair_decimal_odds=fair_decimals,
        fair_american_odds=fair_americans,
        overround=round(overround, 6),
        method=method,
        extra_params=extra_params or {},
        raw_implied_probs=[round(q, 6) for q in raw_probs],
        warning=warning,
    )


# ==============================================================================
# Devigging Algorithms
# ==============================================================================

def devig_multiplicative(
    odds: list[float | int] | Sequence[float | int],
    odds_type: str = "decimal",
) -> DevigResult:
    """
    Multiplicative (Proportional / Normalized Implied) devigging.
    Formulation: p_i = q_i / sum(q_j) = q_i / S
    """
    decimals = _normalize_odds_input(odds, odds_type)
    raw_probs = [1.0 / d for d in decimals]
    s = sum(raw_probs)
    fair_probs = [q / s for q in raw_probs]

    return _build_devig_result(
        probs=fair_probs,
        overround=s,
        method=DevigMethod.MULTIPLICATIVE.value,
        raw_probs=raw_probs,
    )


def devig_additive(
    odds: list[float | int] | Sequence[float | int],
    odds_type: str = "decimal",
    fallback_on_violation: bool = True,
) -> DevigResult:
    """
    Additive (Equal Margin) devigging with non-negative probability guardrail.
    Formulation: p_i = q_i - (S - 1.0) / n
    """
    decimals = _normalize_odds_input(odds, odds_type)
    raw_probs = [1.0 / d for d in decimals]
    n = len(raw_probs)
    s = sum(raw_probs)
    delta = (s - 1.0) / n

    fair_probs = [q - delta for q in raw_probs]
    warning: str | None = None

    # Check boundary conditions
    if any(p <= 0.0 for p in fair_probs):
        if not fallback_on_violation:
            raise ValueError(f"Additive devigging produced non-positive probability: {fair_probs}")
        # Safe fallback to Multiplicative
        fallback_res = devig_multiplicative(decimals, odds_type="decimal")
        extra = dict(fallback_res.extra_params)
        extra["fallback_from"] = "additive"
        extra["fallback_reason"] = "negative_probability"
        extra["delta"] = round(delta, 6)
        warning = "Additive devigging produced non-positive probability; fell back to Multiplicative."
        return _build_devig_result(
            probs=fallback_res.fair_implied_probs,
            overround=s,
            method=DevigMethod.ADDITIVE.value,
            raw_probs=raw_probs,
            extra_params=extra,
            warning=warning,
        )
    elif min(raw_probs) <= 0.05 or s <= 1.0:
        warning = "Longshot boundary condition detected in additive devigging."

    return _build_devig_result(
        probs=fair_probs,
        overround=s,
        method=DevigMethod.ADDITIVE.value,
        raw_probs=raw_probs,
        extra_params={"delta": round(delta, 6)},
        warning=warning,
    )


def devig_power(
    odds: list[float | int] | Sequence[float | int],
    odds_type: str = "decimal",
    tol: float = 1e-12,
) -> DevigResult:
    """
    Power (Geometric / Logarithmic) devigging solving sum(q_i^k) = 1.0.
    Handles standard positive-vig markets (k > 1), fair markets (k = 1),
    and arbitrage / negative-vig markets (0 < k < 1).
    """
    decimals = _normalize_odds_input(odds, odds_type)
    raw_probs = [1.0 / d for d in decimals]
    s = sum(raw_probs)

    # Edge case: zero vig / fair market
    if abs(s - 1.0) < 1e-9:
        return _build_devig_result(
            probs=raw_probs,
            overround=s,
            method=DevigMethod.POWER.value,
            raw_probs=raw_probs,
            extra_params={"k": 1.0, "iterations": 0},
        )

    def f_power(k: float) -> float:
        return sum(q ** k for q in raw_probs) - 1.0

    # Determine bracketing based on overround
    if s > 1.0:
        a, b = 1.0, 100.0
        # If right bracket is not negative, expand
        if f_power(b) > 0:
            b = 500.0
    else:
        # Arbitrage / Negative vig market (S < 1.0)
        a, b = 1e-6, 1.0

    k_root, iters = _brentq(f_power, a, b, xtol=tol)
    fair_probs = [q ** k_root for q in raw_probs]

    return _build_devig_result(
        probs=fair_probs,
        overround=s,
        method=DevigMethod.POWER.value,
        raw_probs=raw_probs,
        extra_params={"k": round(k_root, 6), "iterations": iters},
    )


def devig_shin(
    odds: list[float | int] | Sequence[float | int],
    odds_type: str = "decimal",
    tol: float = 1e-12,
) -> DevigResult:
    """
    Shin (Informed Trader Microstructure) devigging with conjugate numerical stabilization.
    Solves sum(p_i(z)) = 1.0 for informed trader fraction z in [0.0, 1.0).
    Uses the conjugate rationalized formula:
        sqrt(p_i(z)) = (2 * q_i) / (sqrt(z^2 + 4(1-z)q_i) + z)
    to eliminate floating-point cancellation and division-by-zero singularities as z -> 1.
    """
    decimals = _normalize_odds_input(odds, odds_type)
    raw_probs = [1.0 / d for d in decimals]
    s = sum(raw_probs)

    # Edge case: zero vig or arbitrage (S <= 1.0) -> z = 0.0 (Multiplicative degeneration)
    if s <= 1.000000001:
        return _build_devig_result(
            probs=[q / s for q in raw_probs],
            overround=s,
            method=DevigMethod.SHIN.value,
            raw_probs=raw_probs,
            extra_params={"z": 0.0, "iterations": 0},
        )

    def calc_p_shin(z: float) -> list[float]:
        res = []
        for q in raw_probs:
            denom = math.sqrt(z * z + 4.0 * (1.0 - z) * q) + z
            u = (2.0 * q) / denom
            res.append(u * u)
        return res

    def g_shin(z: float) -> float:
        return sum(calc_p_shin(z)) - 1.0

    z_max = 1.0 - 1e-7
    if g_shin(z_max) >= 0.0:
        # Extreme overround edge-case where z -> 1.0
        z_root = z_max
        iters = 0
    else:
        z_root, iters = _brentq(g_shin, 0.0, z_max, xtol=tol)

    fair_probs = calc_p_shin(z_root)

    return _build_devig_result(
        probs=fair_probs,
        overround=s,
        method=DevigMethod.SHIN.value,
        raw_probs=raw_probs,
        extra_params={"z": round(z_root, 6), "iterations": iters},
    )


def devig(
    odds: list[float | int] | Sequence[float | int],
    method: str | DevigMethod = "shin",
    odds_type: str = "decimal",
    **kwargs: Any,
) -> DevigResult:
    """
    Unified entrypoint for all quantitative devigging algorithms.

    Args:
        odds: List of decimal odds (> 1.0) or American odds (integers != 0, |A| >= 100).
        method: Devigging algorithm ('shin', 'power', 'multiplicative'/'proportional', 'additive'/'equal_margin').
        odds_type: 'decimal' or 'american' (case-insensitive).
        **kwargs: Additional parameters (e.g. tol, fallback_on_violation).

    Returns:
        DevigResult: Structured container with fair probabilities, fair odds, overround, and metadata.
    """
    method_str = method.value if isinstance(method, DevigMethod) else str(method).lower().strip()

    if method_str in ("shin",):
        return devig_shin(odds, odds_type=odds_type, **kwargs)
    elif method_str in ("power", "power_devig"):
        return devig_power(odds, odds_type=odds_type, **kwargs)
    elif method_str in ("multiplicative", "proportional", "mult", "normalized"):
        return devig_multiplicative(odds, odds_type=odds_type)
    elif method_str in ("additive", "equal_margin", "add"):
        return devig_additive(odds, odds_type=odds_type, **kwargs)
    else:
        raise ValueError(
            f"Unsupported devigging method '{method}'. Supported methods: 'shin', 'power', 'multiplicative', 'additive'."
        )


class DevigEngine:
    """
    Unified OOP / Namespace wrapper for quantitative devigging and odds utilities.
    """
    @staticmethod
    def devig(
        odds: list[float | int] | Sequence[float | int],
        method: str | DevigMethod = DevigMethod.SHIN,
        odds_type: str = "decimal",
        **kwargs: Any,
    ) -> DevigResult:
        return devig(odds, method=method, odds_type=odds_type, **kwargs)

    @staticmethod
    def multiplicative(
        odds: list[float | int] | Sequence[float | int],
        odds_type: str = "decimal",
    ) -> DevigResult:
        return devig_multiplicative(odds, odds_type=odds_type)

    @staticmethod
    def additive(
        odds: list[float | int] | Sequence[float | int],
        odds_type: str = "decimal",
        **kwargs: Any,
    ) -> DevigResult:
        return devig_additive(odds, odds_type=odds_type, **kwargs)

    @staticmethod
    def power(
        odds: list[float | int] | Sequence[float | int],
        odds_type: str = "decimal",
        **kwargs: Any,
    ) -> DevigResult:
        return devig_power(odds, odds_type=odds_type, **kwargs)

    @staticmethod
    def shin(
        odds: list[float | int] | Sequence[float | int],
        odds_type: str = "decimal",
        **kwargs: Any,
    ) -> DevigResult:
        return devig_shin(odds, odds_type=odds_type, **kwargs)

    @staticmethod
    def american_to_decimal(american_odds: int | float) -> float:
        return american_to_decimal(american_odds)

    @staticmethod
    def decimal_to_american(decimal_odds: float) -> int:
        return decimal_to_american(decimal_odds)

    @staticmethod
    def implied_probability(decimal_odds: float) -> float:
        return implied_probability(decimal_odds)

    @staticmethod
    def calculate_overround(decimal_odds_list: list[float] | Sequence[float]) -> float:
        return calculate_overround(decimal_odds_list)

    @staticmethod
    def odds_to_implied_probs(
        odds: list[float | int] | Sequence[float | int],
        odds_type: str = "decimal",
    ) -> list[float]:
        return odds_to_implied_probs(odds, odds_type=odds_type)
