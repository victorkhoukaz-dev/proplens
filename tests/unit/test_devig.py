"""
tests/unit/test_devig.py

Comprehensive test suite for Quantitative Devigging & True Probability Engine.
Covers:
- Tier 1: Odds Conversions, Invariants, and Input Validations
- Tier 2: Balanced 2-Way Markets (-110 / -110 symmetry across all 4 algorithms)
- Tier 3: Asymmetric Markets & Favorite-Longshot Bias Compression
- Tier 4: Multi-Way Markets (3-Way Soccer 1X2, 6-Way Props, 32-Team Futures)
- Tier 5: Arbitrage / Negative Vig and Boundary Guardrails
- Tier 6: Pure Python Brent's Root Solver Direct Verification & Performance
- Tier 7: DevigResult Dataclass Ergonomics & DevigEngine Wrapper
"""
import math
import pytest

from app.core.devig import (
    DevigEngine,
    DevigMethod,
    DevigResult,
    _brentq,
    american_to_decimal,
    calculate_overround,
    decimal_to_american,
    devig,
    devig_additive,
    devig_multiplicative,
    devig_power,
    devig_shin,
    implied_probability,
    odds_to_implied_probs,
)


# ==============================================================================
# Tier 1: Odds Conversions & Input Validation
# ==============================================================================

class TestOddsConversions:
    """Test mathematical accuracy of American and Decimal odds conversions."""

    @pytest.mark.parametrize(
        "american, expected_decimal",
        [
            (100, 2.0),
            (-100, 2.0),
            (150, 2.50),
            (240, 3.40),
            (650, 7.50),
            (2500, 26.0),
            (50000, 501.0),
            (-110, 1.909091),
            (-300, 1.333333),
            (-500, 1.20),
            (-1000, 1.10),
            (-10000, 1.01),
            (-50000, 1.002),
        ],
    )
    def test_american_to_decimal_valid(self, american: int, expected_decimal: float):
        decimal = american_to_decimal(american)
        assert pytest.approx(decimal, abs=1e-5) == expected_decimal

    @pytest.mark.parametrize(
        "decimal, expected_american",
        [
            (2.0, 100),
            (2.50, 150),
            (3.40, 240),
            (7.50, 650),
            (26.0, 2500),
            (501.0, 50000),
            (1.909091, -110),
            (1.333333, -300),
            (1.20, -500),
            (1.10, -1000),
            (1.01, -10000),
            (1.002, -50000),
        ],
    )
    def test_decimal_to_american_valid(self, decimal: float, expected_american: int):
        american = decimal_to_american(decimal)
        assert american == expected_american

    def test_round_trip_american_to_decimal_to_american(self):
        """Verify strict lossless round-tripping for valid American odds."""
        # Positive grid: +100 to +10,000
        for a in [100, 110, 125, 150, 200, 240, 350, 500, 1000, 2500, 5000, 10000, 50000]:
            dec = american_to_decimal(a)
            recovered = decimal_to_american(dec)
            assert recovered == a, f"Round trip failed for positive American odds {a} -> {dec} -> {recovered}"

        # Negative grid: -105 to -50,000 (note: -100 maps to 2.0 which maps to +100 even money)
        assert decimal_to_american(american_to_decimal(-100)) == 100
        for a in [-105, -110, -120, -125, -150, -200, -240, -300, -500, -1000, -2500, -5000, -10000, -50000]:
            dec = american_to_decimal(a)
            recovered = decimal_to_american(dec)
            assert recovered == a, f"Round trip failed for negative American odds {a} -> {dec} -> {recovered}"

    @pytest.mark.parametrize("invalid_american", [0, 50, -50, 99, -99, 1, -1, 42, -75])
    def test_american_to_decimal_invalid_range_raises(self, invalid_american: int):
        with pytest.raises(ValueError, match="cannot be between -100 and \\+100"):
            american_to_decimal(invalid_american)

    @pytest.mark.parametrize("invalid_val", [float("nan"), float("inf"), float("-inf")])
    def test_american_to_decimal_non_finite_raises(self, invalid_val: float):
        with pytest.raises(ValueError, match="Must be a finite number"):
            american_to_decimal(invalid_val)

    @pytest.mark.parametrize("invalid_decimal", [1.0, 0.95, 0.50, 0.0, -1.5, float("nan"), float("inf")])
    def test_decimal_to_american_invalid_raises(self, invalid_decimal: float):
        with pytest.raises(ValueError, match="strictly greater than 1.0"):
            decimal_to_american(invalid_decimal)

    def test_implied_probability_and_overround(self):
        assert pytest.approx(implied_probability(2.0)) == 0.50
        assert pytest.approx(implied_probability(1.909091), abs=1e-5) == 0.523809

        with pytest.raises(ValueError, match="strictly > 1.0"):
            implied_probability(1.0)
        with pytest.raises(ValueError, match="strictly > 1.0"):
            implied_probability(0.8)

        overround = calculate_overround([1.909091, 1.909091])
        assert pytest.approx(overround, abs=1e-4) == 1.047619

        with pytest.raises(ValueError, match="at least 2 outcomes"):
            calculate_overround([1.90])
        with pytest.raises(ValueError, match="at least 2 outcomes"):
            calculate_overround([])

    def test_odds_to_implied_probs(self):
        raw_dec = odds_to_implied_probs([2.0, 2.0], odds_type="decimal")
        assert raw_dec == [0.5, 0.5]

        raw_ame = odds_to_implied_probs([-110, -110], odds_type="american")
        assert len(raw_ame) == 2
        assert pytest.approx(raw_ame[0], abs=1e-4) == 0.52381


# ==============================================================================
# Tier 2: Balanced 2-Way Markets (-110 / -110 Symmetry)
# ==============================================================================

class TestBalancedMarkets:
    """Verify that all 4 devigging algorithms produce exact 50%/50% probabilities on symmetric lines."""

    @pytest.mark.parametrize(
        "method_name",
        ["multiplicative", "additive", "power", "shin"],
    )
    def test_standard_nfl_minus_110_symmetry_american(self, method_name: str):
        odds = [-110, -110]
        res = devig(odds, method=method_name, odds_type="american")

        assert len(res.fair_implied_probs) == 2
        assert pytest.approx(res.fair_implied_probs[0], abs=1e-6) == 0.500000
        assert pytest.approx(res.fair_implied_probs[1], abs=1e-6) == 0.500000
        assert sum(res.fair_implied_probs) == pytest.approx(1.0, abs=1e-6)

        assert res.fair_decimal_odds == [2.0, 2.0]
        assert res.fair_american_odds == [100, 100]
        assert pytest.approx(res.overround, abs=1e-4) == 1.047619
        assert pytest.approx(res.overround_pct, abs=1e-2) == 4.7619
        assert pytest.approx(res.margin_pct, abs=1e-2) == 4.5455
        assert pytest.approx(res.vig_pct, abs=1e-2) == 4.5455

    @pytest.mark.parametrize(
        "method_name",
        ["multiplicative", "additive", "power", "shin"],
    )
    def test_even_money_plus_100_symmetry(self, method_name: str):
        odds = [2.0, 2.0]
        res = devig(odds, method=method_name, odds_type="decimal")

        assert res.fair_implied_probs == [0.5, 0.5]
        assert res.fair_decimal_odds == [2.0, 2.0]
        assert res.fair_american_odds == [100, 100]
        assert pytest.approx(res.overround, abs=1e-6) == 1.000000
        assert res.overround_pct == 0.0
        assert res.margin_pct == 0.0

    @pytest.mark.parametrize(
        "method_name",
        ["multiplicative", "additive", "power", "shin"],
    )
    def test_heavy_juice_symmetric_market(self, method_name: str):
        # Heavy juice 2-way market: -200 / -200 (D = 1.50 / 1.50, Overround = 1.3333)
        odds = [1.50, 1.50]
        res = devig(odds, method=method_name, odds_type="decimal")

        assert pytest.approx(res.fair_implied_probs[0], abs=1e-6) == 0.50
        assert pytest.approx(res.fair_implied_probs[1], abs=1e-6) == 0.50
        assert sum(res.fair_implied_probs) == pytest.approx(1.0, abs=1e-6)
        assert res.fair_american_odds == [100, 100]


# ==============================================================================
# Tier 3: Asymmetric Markets & Favorite-Longshot Bias
# ==============================================================================

class TestAsymmetricMarkets:
    """
    Verify favorite-longshot bias behavior in asymmetric markets:
    Shin and Power compress the longshot probability and expand the favorite probability
    relative to Multiplicative devigging.
    """

    def test_moderate_asymmetric_market_minus_300_plus_240(self):
        # Odds: -300 / +240 -> D = [1.333333, 3.400000]
        odds = [-300, 240]

        res_mult = devig_multiplicative(odds, odds_type="american")
        res_add = devig_additive(odds, odds_type="american")
        res_pow = devig_power(odds, odds_type="american")
        res_shin = devig_shin(odds, odds_type="american")

        # Verify sum to 1.0 across all methods
        for res in [res_mult, res_add, res_pow, res_shin]:
            assert sum(res.fair_implied_probs) == pytest.approx(1.0, abs=1e-6)
            assert 0.0 < res.fair_implied_probs[0] < 1.0
            assert 0.0 < res.fair_implied_probs[1] < 1.0

        # Multiplicative baseline: ~71.83% fav / ~28.17% dog
        p_fav_mult = res_mult.fair_implied_probs[0]
        p_dog_mult = res_mult.fair_implied_probs[1]
        assert pytest.approx(p_fav_mult, abs=1e-3) == 0.7183
        assert pytest.approx(p_dog_mult, abs=1e-3) == 0.2817

        # Shin model: ~73.55% fav / ~26.45% dog
        p_fav_shin = res_shin.fair_implied_probs[0]
        p_dog_shin = res_shin.fair_implied_probs[1]
        assert pytest.approx(p_fav_shin, abs=1e-3) == 0.7355
        assert pytest.approx(p_dog_shin, abs=1e-3) == 0.2645
        assert res_shin.z_parameter is not None
        assert 0.05 < res_shin.z_parameter < 0.20

        # Power model: ~73.31% fav / ~26.69% dog
        p_fav_pow = res_pow.fair_implied_probs[0]
        p_dog_pow = res_pow.fair_implied_probs[1]
        assert pytest.approx(p_fav_pow, abs=1e-3) == 0.7331
        assert pytest.approx(p_dog_pow, abs=1e-3) == 0.2669
        assert res_pow.k_parameter is not None
        assert res_pow.k_parameter > 1.0

        # Key Favorite-Longshot Bias Invariant:
        # Shin and Power allocate more probability to the favorite and less to the longshot than Multiplicative
        assert p_fav_shin > p_fav_mult
        assert p_dog_shin < p_dog_mult
        assert p_fav_pow > p_fav_mult
        assert p_dog_pow < p_dog_mult

    def test_heavy_asymmetric_market_minus_500_plus_350(self):
        # Odds: -500 / +350 -> D = [1.20, 4.50]
        odds = [-500, 350]

        res_mult = devig_multiplicative(odds, odds_type="american")
        res_shin = devig_shin(odds, odds_type="american")
        res_pow = devig_power(odds, odds_type="american")

        assert sum(res_mult.fair_implied_probs) == pytest.approx(1.0, abs=1e-6)
        assert sum(res_shin.fair_implied_probs) == pytest.approx(1.0, abs=1e-6)
        assert sum(res_pow.fair_implied_probs) == pytest.approx(1.0, abs=1e-6)

        # Shin favorite probability > Multiplicative favorite probability
        assert res_shin.fair_implied_probs[0] > res_mult.fair_implied_probs[0]
        assert res_shin.fair_implied_probs[1] < res_mult.fair_implied_probs[1]

    def test_extreme_favorite_minus_10000_plus_2500(self):
        # D = [1.01, 26.0]
        odds = [-10000, 2500]

        res_shin = devig_shin(odds, odds_type="american")
        res_pow = devig_power(odds, odds_type="american")
        res_mult = devig_multiplicative(odds, odds_type="american")

        assert sum(res_shin.fair_implied_probs) == pytest.approx(1.0, abs=1e-6)
        assert res_shin.fair_implied_probs[0] > 0.98  # Fav gets near 98.5%
        assert res_shin.fair_implied_probs[1] < 0.02  # Dog gets ~1.4%
        assert res_shin.fair_implied_probs[0] > res_mult.fair_implied_probs[0]


# ==============================================================================
# Tier 4: Multi-Way Markets (Soccer 1X2, Multi-Prop, Futures)
# ==============================================================================

class TestMultiWayMarkets:
    """Verify numerical convergence and probability conservation on N-way markets."""

    def test_3way_soccer_1x2(self):
        # Odds: Home 2.50 (+150), Draw 3.20 (+220), Away 2.80 (+180)
        odds = [2.50, 3.20, 2.80]

        for method in [DevigMethod.MULTIPLICATIVE, DevigMethod.ADDITIVE, DevigMethod.POWER, DevigMethod.SHIN]:
            res = devig(odds, method=method, odds_type="decimal")
            assert len(res.fair_implied_probs) == 3
            assert sum(res.fair_implied_probs) == pytest.approx(1.0, abs=1e-5)
            # Rank preservation: Home (2.50) > Away (2.80) > Draw (3.20)
            assert res.fair_implied_probs[0] > res.fair_implied_probs[2] > res.fair_implied_probs[1]
            assert all(d > 1.0 for d in res.fair_decimal_odds)

    def test_6way_first_td_market(self):
        # Odds: [4.50, 5.50, 8.00, 10.00, 15.00, 2.20]
        odds = [4.50, 5.50, 8.00, 10.00, 15.00, 2.20]

        res_shin = devig_shin(odds, odds_type="decimal")
        res_pow = devig_power(odds, odds_type="decimal")
        res_mult = devig_multiplicative(odds, odds_type="decimal")

        assert sum(res_shin.fair_implied_probs) == pytest.approx(1.0, abs=1e-6)
        assert sum(res_pow.fair_implied_probs) == pytest.approx(1.0, abs=1e-6)
        assert sum(res_mult.fair_implied_probs) == pytest.approx(1.0, abs=1e-6)

        # Field/Favorite (2.20) is index 5
        assert res_shin.fair_implied_probs[5] == res_shin.favorite_prob
        # Longshot (15.00) is index 4
        assert res_shin.fair_implied_probs[4] == res_shin.longshot_prob
        # Under Shin/Power, longshot true probability is compressed vs multiplicative
        assert res_shin.fair_implied_probs[4] < res_mult.fair_implied_probs[4]

    def test_32_team_nfl_futures_scale(self):
        # 32 NFL teams with odds ranging from +450 (Chiefs) to +30000 (Panthers)
        american_odds = [
            450, 550, 600, 750, 900, 1000, 1200, 1400,
            1600, 1800, 2000, 2200, 2500, 2800, 3000, 3500,
            4000, 4500, 5000, 6000, 7000, 8000, 9000, 10000,
            12500, 15000, 17500, 20000, 22500, 25000, 27500, 30000,
        ]

        res_shin = devig_shin(american_odds, odds_type="american")
        res_pow = devig_power(american_odds, odds_type="american")
        res_mult = devig_multiplicative(american_odds, odds_type="american")

        assert len(res_shin.fair_implied_probs) == 32
        assert sum(res_shin.fair_implied_probs) == pytest.approx(1.0, abs=1e-5)
        assert sum(res_pow.fair_implied_probs) == pytest.approx(1.0, abs=1e-5)
        assert sum(res_mult.fair_implied_probs) == pytest.approx(1.0, abs=1e-5)

        # Strict monotonicity across 32 teams
        for i in range(len(res_shin.fair_implied_probs) - 1):
            assert res_shin.fair_implied_probs[i] > res_shin.fair_implied_probs[i + 1]


# ==============================================================================
# Tier 5: Arbitrage / Negative Vig & Guardrails
# ==============================================================================

class TestArbitrageAndGuardrails:
    """Verify behavior on negative-vig (arbitrage) markets and additive boundary fallbacks."""

    def test_arbitrage_negative_vig_market(self):
        # Two books quoting +110 / +110 -> D = [2.10, 2.10], Overround = 0.952381 (< 1.0)
        odds = [2.10, 2.10]

        res_mult = devig_multiplicative(odds, odds_type="decimal")
        res_add = devig_additive(odds, odds_type="decimal")
        res_pow = devig_power(odds, odds_type="decimal")
        res_shin = devig_shin(odds, odds_type="decimal")

        assert res_mult.fair_implied_probs == [0.5, 0.5]
        assert res_add.fair_implied_probs == [0.5, 0.5]
        assert res_pow.fair_implied_probs == [0.5, 0.5]
        assert res_shin.fair_implied_probs == [0.5, 0.5]

        # In arbitrage, Shin clamps z = 0.0
        assert res_shin.z_parameter == 0.0
        # In arbitrage, Power exponent k < 1.0
        assert res_pow.k_parameter is not None and res_pow.k_parameter < 1.0

    def test_additive_boundary_violation_fallback(self):
        # Extreme disparity where delta > min(raw_prob)
        # e.g. 5-way market with heavy favorite and 4 extreme longshots
        odds = [1.10, 50.0, 50.0, 50.0, 50.0]
        # Overround S = 1/1.10 + 4*(1/50) = 0.90909 + 0.080 = 0.98909
        # Let's create an overround > 1: [1.10, 25.0, 25.0, 25.0, 25.0, 25.0]
        # S = 0.90909 + 5*(0.04) = 1.10909. delta = 0.10909 / 6 = 0.01818.
        # Longshot priced at 100.0 has raw_prob = 0.01 < delta (0.01818), which would yield negative probability.
        odds_violation = [1.10, 25.0, 25.0, 25.0, 25.0, 100.0]

        # With fallback_on_violation=True (default), returns valid probs and sets metadata
        res = devig_additive(odds_violation, odds_type="decimal", fallback_on_violation=True)
        assert sum(res.fair_implied_probs) == pytest.approx(1.0, abs=1e-5)
        assert all(p > 0 for p in res.fair_implied_probs)
        assert res.extra_params.get("fallback_from") == "additive"
        assert res.extra_params.get("fallback_reason") == "negative_probability"

        # With fallback_on_violation=False, raises ValueError
        with pytest.raises(ValueError, match="non-positive probability"):
            devig_additive(odds_violation, odds_type="decimal", fallback_on_violation=False)

    def test_invalid_devig_inputs_raise_errors(self):
        # Empty list
        with pytest.raises(ValueError, match="at least 2 outcomes"):
            devig([], method="shin")

        # Single outcome
        with pytest.raises(ValueError, match="at least 2 outcomes"):
            devig([1.90], method="shin")

        # Non-positive decimal odds
        with pytest.raises(ValueError, match="strictly > 1.0"):
            devig([1.90, -1.50], method="shin")

        # Invalid odds type
        with pytest.raises(ValueError, match="Unsupported odds_type"):
            devig([1.90, 1.90], odds_type="fractional")

        # Unsupported method
        with pytest.raises(ValueError, match="Unsupported devigging method"):
            devig([1.90, 1.90], method="quantum_devig")


# ==============================================================================
# Tier 6: Pure Python Brent's Solver Verification & Performance
# ==============================================================================

class TestBrentqSolver:
    """Direct mathematical unit tests for pure Python _brentq root solver."""

    def test_brentq_linear_root(self):
        # f(x) = 2x - 4 -> root = 2.0
        root, iters = _brentq(lambda x: 2.0 * x - 4.0, 0.0, 5.0)
        assert pytest.approx(root, abs=1e-12) == 2.0
        assert iters < 10

    def test_brentq_cubic_root(self):
        # f(x) = x^3 - x - 2 -> root approx 1.5213797068
        root, iters = _brentq(lambda x: x ** 3 - x - 2.0, 1.0, 2.0)
        assert pytest.approx(root, abs=1e-8) == 1.5213797068
        assert iters < 15

    def test_brentq_unbracketed_raises(self):
        # f(x) = x^2 + 1 (no real root)
        with pytest.raises(ValueError, match="Root not bracketed"):
            _brentq(lambda x: x * x + 1.0, -1.0, 1.0)


# ==============================================================================
# Tier 7: Dataclass Ergonomics & DevigEngine Wrapper
# ==============================================================================

class TestDataclassAndEngineWrapper:
    """Verify DevigResult property helpers and DevigEngine static methods."""

    def test_devig_result_properties_and_serialization(self):
        res = devig([-110, -110], method="shin", odds_type="american")

        assert res.fair_implied_probabilities == res.fair_implied_probs
        assert res.true_probs == res.fair_implied_probs
        assert res.z_parameter is not None
        assert res.overround_pct > 0.0
        assert res.margin_pct > 0.0
        assert res.vig_pct == res.margin_pct
        assert res.favorite_prob == 0.5
        assert res.longshot_prob == 0.5

        d = res.to_dict()
        assert isinstance(d, dict)
        assert d["method"] == "shin"
        assert len(d["fair_implied_probs"]) == 2
        assert len(d["fair_decimal_odds"]) == 2
        assert len(d["fair_american_odds"]) == 2

    def test_devig_engine_class_methods(self):
        res_shin = DevigEngine.shin([-110, -110], odds_type="american")
        assert res_shin.method == "shin"

        res_pow = DevigEngine.power([1.909091, 1.909091], odds_type="decimal")
        assert res_pow.method == "power"

        res_mult = DevigEngine.multiplicative([1.909091, 1.909091])
        assert res_mult.method == "multiplicative"

        res_add = DevigEngine.additive([1.909091, 1.909091])
        assert res_add.method == "additive"

        res_gen = DevigEngine.devig([-300, 240], method=DevigMethod.SHIN, odds_type="american")
        assert res_gen.method == "shin"

        # Static utility wrappers
        assert DevigEngine.american_to_decimal(100) == 2.0
        assert DevigEngine.decimal_to_american(2.0) == 100
        assert DevigEngine.implied_probability(2.0) == 0.5
        assert pytest.approx(DevigEngine.calculate_overround([2.0, 2.0])) == 1.0
        assert DevigEngine.odds_to_implied_probs([2.0, 2.0]) == [0.5, 0.5]
