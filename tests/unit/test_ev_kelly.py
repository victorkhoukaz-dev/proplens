"""
tests/unit/test_ev_kelly.py

Comprehensive Unit Test Suite for Dual-Edge EV+ Engine & Fractional Kelly Sizing.
Milestone: M4 (Dual-Edge EV+ Engine & Fractional Kelly Sizing)

Covers:
- Tier 1: Standard EV on No-Push Lines (+100, -110, +150, -200, +500)
- Tier 2: Push-Adjusted EV on Integer Lines (Totals, spreads, player props, continuity)
- Tier 3: Market-Implied vs Model-Implied vs Blended EV (Convex combinations, fallbacks)
- Tier 4: Fractional Kelly Bet Sizing (Full, Half, Quarter, Eighth Kelly across $1k, $10k, $50k bankrolls)
- Tier 5: Guardrails & Risk Constraints (Non-positive EV, 5% max cap, $5 min threshold)
- Tier 6: Edge Cases & Boundary Validations (0%, 100%, D <= 1.0, +10000, -10000, invalid inputs)
- Tier 7: Integration Bridges with DevigResult & DistributionResult, EVResult Pydantic conformance
"""
import math
import time
import pytest

from app.core.devig import DevigEngine, DevigMethod, DevigResult
from app.core.distributions import DistributionEngine, DistributionResult, DistributionType
from app.core.ev import (
    EVEngine,
    EVResult,
    KellyConfig,
    KellySizingMode,
    blend_probabilities,
    calculate_ev,
    calculate_fractional_kelly,
    calculate_stake,
    from_devig_and_distribution,
)
from app.schemas.ev import EVResult as SchemaEVResult


# ==============================================================================
# Tier 1: Standard EV Calculations on No-Push Lines
# ==============================================================================

class TestStandardEVCalculations:
    """Test suite verifying exact EV calculations on standard half-point (no-push) lines."""

    @pytest.mark.parametrize(
        "decimal_odds, win_prob, expected_ev_pct",
        [
            (2.000000, 0.500000, 0.00),     # Coin flip fair (Zero EV)
            (2.000000, 0.550000, 10.00),    # Coin flip +10% EV
            (2.000000, 0.450000, -10.00),   # Coin flip -10% EV
            (1.909091, 0.523810, 0.00),     # -110 break-even fair
            (1.909091, 0.550000, 5.00),     # -110 +5% EV
            (1.909091, 0.500000, -4.55),    # -110 standard juice loss
            (2.500000, 0.450000, 12.50),    # +150 underdog +12.5% EV
            (1.500000, 0.700000, 5.00),     # -200 favorite +5.0% EV
            (6.000000, 0.200000, 20.00),    # +500 longshot +20.0% EV
        ],
    )
    def test_standard_ev_formula(self, decimal_odds: float, win_prob: float, expected_ev_pct: float):
        res = EVEngine.calculate(
            decimal_odds=decimal_odds,
            p_market_fair=win_prob,
            p_push=0.0,
        )
        assert res.blended_ev == pytest.approx(expected_ev_pct, abs=1e-2)
        assert res.edge_pct == pytest.approx(expected_ev_pct, abs=1e-2)
        assert res.ev_decimal == pytest.approx(expected_ev_pct / 100.0, abs=1e-4)

    def test_single_ev_function(self):
        """Verify standalone calculate_ev and calculate_single_ev functions."""
        ev_dec = EVEngine.calculate_single_ev(p_win=0.55, decimal_odds=2.0, p_push=0.0)
        assert ev_dec == pytest.approx(0.10, abs=1e-6)

        ev_func_dec = calculate_ev(0.55, 2.0, 0.0)
        assert ev_func_dec == pytest.approx(0.10, abs=1e-6)

    def test_ev_monotonicity_with_win_probability(self):
        """Verify EV strictly increases as win probability increases."""
        odds = 1.909091
        ev_low = EVEngine.calculate(odds, p_market_fair=0.50).blended_ev
        ev_mid = EVEngine.calculate(odds, p_market_fair=0.53).blended_ev
        ev_high = EVEngine.calculate(odds, p_market_fair=0.58).blended_ev
        assert ev_low < ev_mid < ev_high


# ==============================================================================
# Tier 2: Push-Adjusted EV on Whole Integer Lines
# ==============================================================================

class TestPushAdjustedEV:
    """Test suite verifying push mechanics and refund math on whole integer lines."""

    def test_nfl_totals_integer_push_reversal(self):
        """Demonstrate that an 8% push refund flips a 50% bet on -110 from -EV to +EV."""
        odds = 1.909091  # -110
        # No push: EV = (0.50 * 1.909091) - 1 = -4.55%
        res_no_push = EVEngine.calculate(odds, p_market_fair=0.50, p_push=0.0)
        assert res_no_push.blended_ev == pytest.approx(-4.55, abs=1e-2)
        assert res_no_push.is_positive_ev is False

        # 8% Push: EV = (0.50 * 1.909091) - (1 - 0.08) = 0.954545 - 0.92 = +3.45%
        res_with_push = EVEngine.calculate(odds, p_market_fair=0.50, p_push=0.08)
        assert res_with_push.blended_ev == pytest.approx(3.45, abs=1e-2)
        assert res_with_push.is_positive_ev is True

    def test_push_break_even_probability(self):
        """Verify break-even win probability formula: p_be = (1 - p_push) / D."""
        odds = 1.909091
        p_push = 0.08
        p_be = (1.0 - p_push) / odds  # ~0.481905
        res = EVEngine.calculate(odds, p_market_fair=p_be, p_push=p_push)
        assert res.blended_ev == pytest.approx(0.00, abs=1e-2)

    def test_discrete_count_prop_push_receptions(self):
        """Discrete reception prop: Line 5.0 receptions, 15% push probability."""
        odds = 2.10  # +110
        p_win = 0.45
        p_push = 0.15
        # EV = (0.45 * 2.10) - (1 - 0.15) = 0.945 - 0.85 = +0.0950 (+9.50%)
        res = EVEngine.calculate(odds, p_market_fair=p_win, p_push=p_push)
        assert res.blended_ev == pytest.approx(9.50, abs=1e-2)

    def test_continuous_yardage_continuity_push(self):
        """Continuous yardage prop: Line 65.0 yards, 1.2% push probability."""
        odds = 1.909091
        p_win = 0.53
        p_push = 0.012
        # EV = (0.53 * 1.909091) - (1 - 0.012) = 1.011818 - 0.988000 = +0.023818 (+2.38%)
        res = EVEngine.calculate(odds, p_market_fair=p_win, p_push=p_push)
        assert res.blended_ev == pytest.approx(2.38, abs=1e-2)

    def test_push_zero_invariant_match(self):
        """Verify prob_push=0.0 produces identical results to default zero push."""
        res_explicit_zero = EVEngine.calculate(2.0, p_market_fair=0.55, p_push=0.0)
        res_default_zero = EVEngine.calculate(2.0, p_market_fair=0.55)
        assert res_explicit_zero.blended_ev == res_default_zero.blended_ev == pytest.approx(10.00, abs=1e-2)


# ==============================================================================
# Tier 3: Market-Implied vs Model-Implied vs Blended EV
# ==============================================================================

class TestSignalWeightingAndFallbacks:
    """Test suite for dual-signal consensus blending and graceful degradation fallbacks."""

    def test_default_60_40_blending(self):
        """Market: 54% (+8% EV), Model: 51% (+2% EV) -> Blend: 52.8% (+5.6% EV)."""
        res = EVEngine.calculate(
            decimal_odds=2.00,
            p_market_fair=0.54,
            p_model_fair=0.51,
            w_market=0.60,
            w_model=0.40,
        )
        assert res.market_implied_ev == pytest.approx(8.00, abs=1e-2)
        assert res.model_implied_ev == pytest.approx(2.00, abs=1e-2)
        assert res.blended_win_prob == pytest.approx(0.5280, abs=1e-4)
        assert res.blended_ev == pytest.approx(5.60, abs=1e-2)

    def test_conflicting_signals_dampening(self):
        """Market indicates +10% EV, Model indicates -10% EV -> Blend produces +2% EV."""
        res = EVEngine.calculate(
            decimal_odds=2.00,
            p_market_fair=0.55,
            p_model_fair=0.45,
            w_market=0.60,
            w_model=0.40,
        )
        assert res.market_implied_ev == pytest.approx(10.00, abs=1e-2)
        assert res.model_implied_ev == pytest.approx(-10.00, abs=1e-2)
        assert res.blended_ev == pytest.approx(2.00, abs=1e-2)

    def test_unnormalized_weights_handling(self):
        """Weights (3.0, 2.0) should automatically normalize to (0.60, 0.40)."""
        res = EVEngine.calculate(
            decimal_odds=2.00,
            p_market_fair=0.54,
            p_model_fair=0.51,
            w_market=3.0,
            w_model=2.0,
        )
        assert res.blended_win_prob == pytest.approx(0.5280, abs=1e-4)
        assert res.blended_ev == pytest.approx(5.60, abs=1e-2)

    def test_market_only_fallback(self):
        """When model_fair_prob is None, fallback seamlessly to market probability."""
        res = EVEngine.calculate(
            decimal_odds=2.00,
            p_market_fair=0.54,
            p_model_fair=None,
        )
        assert res.market_implied_ev == pytest.approx(8.00, abs=1e-2)
        assert res.model_implied_ev is None
        assert res.blended_win_prob == pytest.approx(0.5400, abs=1e-4)
        assert res.blended_ev == pytest.approx(8.00, abs=1e-2)

    def test_model_only_fallback(self):
        """When market_fair_prob is None, fallback seamlessly to model probability."""
        res = EVEngine.calculate(
            decimal_odds=2.00,
            p_market_fair=None,
            p_model_fair=0.52,
        )
        assert res.market_implied_ev is None
        assert res.model_implied_ev == pytest.approx(4.00, abs=1e-2)
        assert res.blended_win_prob == pytest.approx(0.5200, abs=1e-4)
        assert res.blended_ev == pytest.approx(4.00, abs=1e-2)

    def test_zero_weight_overrides(self):
        """Setting w_market=0 forces 100% model reliance even if market is supplied."""
        res = EVEngine.calculate(
            decimal_odds=2.00,
            p_market_fair=0.55,
            p_model_fair=0.52,
            w_market=0.0,
            w_model=1.0,
        )
        assert res.blended_win_prob == pytest.approx(0.5200, abs=1e-4)
        assert res.blended_ev == pytest.approx(4.00, abs=1e-2)

    def test_blended_signals_with_push(self):
        """Dual signal evaluation with integer push probability."""
        res = EVEngine.calculate(
            decimal_odds=1.909091,
            p_market_fair=0.51,
            p_model_fair=0.49,
            p_push=0.08,
            w_market=0.60,
            w_model=0.40,
        )
        # Blend p = 0.6*0.51 + 0.4*0.49 = 0.502
        # EV = (0.502 * 1.909091 - 0.92) * 100 = +3.84%
        assert res.blended_win_prob == pytest.approx(0.5020, abs=1e-4)
        assert res.blended_ev == pytest.approx(3.84, abs=1e-2)

    def test_missing_both_signals_raises(self):
        """Supplying neither market nor model prob must raise ValueError."""
        with pytest.raises(ValueError, match="At least one probability signal must be provided"):
            EVEngine.calculate(decimal_odds=2.00, p_market_fair=None, p_model_fair=None)


# ==============================================================================
# Tier 4: Fractional Kelly Criterion & Bet Sizing
# ==============================================================================

class TestFractionalKellySizing:
    """Test suite for Kelly fraction derivation and multi-bankroll stake sizing."""

    def test_kelly_fractions_even_money(self):
        # D = 2.0, p = 0.55 -> EV = +10.0% -> f* = 0.10 / 1.0 = 0.10
        res = EVEngine.calculate(decimal_odds=2.00, p_market_fair=0.55, bankroll=1000.0)
        assert res.full_kelly_fraction == pytest.approx(0.1000, abs=1e-4)
        assert res.half_kelly_fraction == pytest.approx(0.0500, abs=1e-4)
        assert res.quarter_kelly_fraction == pytest.approx(0.0250, abs=1e-4)
        assert res.eighth_kelly_fraction == pytest.approx(0.0125, abs=1e-4)

    def test_kelly_fractions_standard_juice(self):
        # D = 1.909091, p = 0.55 -> EV = +5.0% -> f* = 0.05 / 0.909091 = 0.0550
        res = EVEngine.calculate(decimal_odds=1.909091, p_market_fair=0.55, bankroll=1000.0)
        assert res.full_kelly_fraction == pytest.approx(0.0550, abs=1e-4)
        assert res.half_kelly_fraction == pytest.approx(0.0275, abs=1e-4)
        assert res.quarter_kelly_fraction == pytest.approx(0.01375, abs=1e-4)

    @pytest.mark.parametrize(
        "bankroll, expected_quarter_stake, expected_half_stake, expected_full_stake",
        [
            (1000.0, 13.75, 27.50, 50.00),     # Full capped at 5% ($50)
            (10000.0, 137.50, 275.00, 500.00), # Full capped at 5% ($500)
            (50000.0, 687.50, 1375.00, 2500.00),# Full capped at 5% ($2500)
        ],
    )
    def test_bankroll_scaling_grid(
        self,
        bankroll: float,
        expected_quarter_stake: float,
        expected_half_stake: float,
        expected_full_stake: float,
    ):
        """Verify proportional dollar scaling across diverse bankrolls ($1k, $10k, $50k)."""
        res = EVEngine.calculate(
            decimal_odds=1.909091,
            p_market_fair=0.55,
            bankroll=bankroll,
            max_allocation_pct=0.05,
        )
        assert res.quarter_kelly_stake == pytest.approx(expected_quarter_stake, abs=0.01)
        assert res.half_kelly_stake == pytest.approx(expected_half_stake, abs=0.01)
        assert res.full_kelly_stake == pytest.approx(expected_full_stake, abs=0.01)
        assert res.recommended_stake == pytest.approx(expected_quarter_stake, abs=0.01)

    def test_custom_fractional_kelly_multiplier(self):
        """Test Eighth Kelly (0.125) configuration."""
        res = EVEngine.calculate(
            decimal_odds=2.00,
            p_market_fair=0.55,
            bankroll=10000.0,
            fraction=0.125,
        )
        # f* = 0.10 -> Eighth Kelly = 0.0125 -> Stake = $125.00
        assert res.recommended_stake == pytest.approx(125.00, abs=0.01)

    def test_standalone_kelly_fraction_function(self):
        """Verify calculate_fractional_kelly helper function."""
        f_full = calculate_fractional_kelly(ev_decimal=0.10, decimal_odds=2.00, fraction=1.0)
        assert f_full == pytest.approx(0.10, abs=1e-5)

        f_half = calculate_fractional_kelly(ev_decimal=0.10, decimal_odds=2.00, fraction=0.5)
        assert f_half == pytest.approx(0.05, abs=1e-5)


# ==============================================================================
# Tier 5: Guardrails & Risk Constraints
# ==============================================================================

class TestGuardrailsAndRiskConstraints:
    """Test suite verifying safety constraints (EV <= 0, max allocation caps, min thresholds)."""

    def test_negative_ev_produces_zero_stake(self):
        """Negative EV bets must strictly yield 0.0 fraction and $0.00 stake."""
        res = EVEngine.calculate(decimal_odds=1.909091, p_market_fair=0.50, bankroll=10000.0)
        assert res.blended_ev < 0
        assert res.quarter_kelly_fraction == 0.0
        assert res.full_kelly_stake == 0.0
        assert res.recommended_stake == 0.0
        assert res.is_positive_ev is False

    def test_zero_ev_produces_zero_stake(self):
        """Fair bets (0% EV) must yield 0.0 fraction and $0.00 stake."""
        res = EVEngine.calculate(decimal_odds=2.00, p_market_fair=0.50, bankroll=10000.0)
        assert res.blended_ev == 0.0
        assert res.quarter_kelly_fraction == 0.0
        assert res.recommended_stake == 0.0
        assert res.is_positive_ev is False

    def test_max_bankroll_allocation_cap_5pct(self):
        """Massive edge (60% Full Kelly) must be capped at 5% of bankroll."""
        # D = 2.0, p = 0.80 -> EV = +60% -> f* = 0.60 (Full), f_Q = 0.15
        # Bankroll = $10,000 -> Raw Quarter Stake = $1,500 -> 5% Cap -> $500.00
        res = EVEngine.calculate(
            decimal_odds=2.00,
            p_market_fair=0.80,
            bankroll=10000.0,
            max_allocation_pct=0.05,
        )
        assert res.quarter_kelly_stake == 500.00
        assert res.half_kelly_stake == 500.00
        assert res.full_kelly_stake == 500.00
        assert res.recommended_stake == 500.00
        assert res.is_capped is True

    def test_absolute_max_stake_cap(self):
        """Absolute dollar ceiling ($250.00) caps large bankroll stakes."""
        res = EVEngine.calculate(
            decimal_odds=2.00,
            p_market_fair=0.70,
            bankroll=20000.0,
            max_allocation_pct=0.05,
            max_stake=250.0,
        )
        # Bankroll $20k * 5% = $1000, but max_stake = $250
        assert res.recommended_stake == 250.00
        assert res.is_capped is True

    def test_min_stake_threshold_suppression(self):
        """Stakes below min_stake ($5.00) must be suppressed to $0.00."""
        # Bankroll = $200, D = 2.0, p = 0.54 -> EV = 8% -> f* = 0.08 -> f_Q = 0.02
        # Raw Quarter Stake = $200 * 0.02 = $4.00 (< $5.00)
        res = EVEngine.calculate(
            decimal_odds=2.00,
            p_market_fair=0.54,
            bankroll=200.0,
            min_stake=5.0,
        )
        assert res.quarter_kelly_stake == 0.0
        assert res.recommended_stake == 0.0

    def test_min_stake_threshold_allowance(self):
        """Stakes meeting or exceeding min_stake ($5.00) must be accepted."""
        # Bankroll = $250 -> Raw Quarter Stake = $250 * 0.02 = $5.00
        res = EVEngine.calculate(
            decimal_odds=2.00,
            p_market_fair=0.54,
            bankroll=250.0,
            min_stake=5.0,
        )
        assert res.quarter_kelly_stake == 5.00
        assert res.recommended_stake == 5.00

    def test_zero_bankroll_handling(self):
        """A bankroll of $0.00 must return $0.00 stakes without errors."""
        res = EVEngine.calculate(decimal_odds=2.00, p_market_fair=0.55, bankroll=0.0)
        assert res.quarter_kelly_fraction == pytest.approx(0.0250, abs=1e-4)
        assert res.recommended_stake == 0.0


# ==============================================================================
# Tier 6: Edge Cases & Boundary Values
# ==============================================================================

class TestEdgeCasesAndBoundaryValidation:
    """Test suite for extreme probabilities, extreme odds, and input validation."""

    def test_zero_win_probability(self):
        res = EVEngine.calculate(decimal_odds=2.00, p_market_fair=0.0)
        assert res.blended_ev == -100.0
        assert res.quarter_kelly_fraction == 0.0
        assert res.recommended_stake == 0.0

    def test_certain_win_probability(self):
        res = EVEngine.calculate(decimal_odds=2.00, p_market_fair=1.0, bankroll=1000.0)
        assert res.blended_ev == 100.0
        assert res.full_kelly_fraction == 1.0
        assert res.recommended_stake == 50.00  # Capped at 5% of $1,000

    def test_certain_push_probability(self):
        res = EVEngine.calculate(decimal_odds=2.00, p_market_fair=0.0, p_push=1.0)
        assert res.blended_ev == 0.0
        assert res.recommended_stake == 0.0

    def test_heavy_favorite_minus_10000(self):
        """Heavy favorite D = 1.01 (-10000), p = 0.995."""
        res = EVEngine.calculate(decimal_odds=1.01, p_market_fair=0.995, bankroll=10000.0)
        # EV = (0.995 * 1.01 - 1) * 100 = +0.495%
        # f* = 0.00495 / 0.01 = 0.4950 -> f_Q = 0.12375
        assert res.blended_ev == pytest.approx(0.495, abs=1e-2)
        assert res.quarter_kelly_fraction == pytest.approx(0.12375, abs=1e-4)
        assert res.recommended_stake == 500.00  # Capped at 5% of $10,000

    def test_massive_longshot_plus_10000(self):
        """Massive longshot D = 101.0 (+10000), p = 0.02."""
        res = EVEngine.calculate(decimal_odds=101.0, p_market_fair=0.02, bankroll=10000.0)
        # EV = (0.02 * 101.0 - 1) * 100 = +102.0%
        # f* = 1.02 / 100.0 = 0.0102 -> f_Q = 0.00255
        # Stake = $10,000 * 0.00255 = $25.50
        assert res.blended_ev == pytest.approx(102.00, abs=1e-2)
        assert res.quarter_kelly_fraction == pytest.approx(0.00255, abs=1e-5)
        assert res.recommended_stake == pytest.approx(25.50, abs=0.01)

    def test_invalid_probability_sum_raises(self):
        with pytest.raises(ValueError, match="Sum of win and push probabilities cannot exceed 1.0"):
            EVEngine.calculate(decimal_odds=2.00, p_market_fair=0.70, p_push=0.40)

    @pytest.mark.parametrize("invalid_prob", [-0.01, 1.01, -0.5])
    def test_out_of_bounds_probabilities_raise(self, invalid_prob: float):
        with pytest.raises(ValueError, match="Probabilities must be between 0.0 and 1.0"):
            EVEngine.calculate(decimal_odds=2.00, p_market_fair=invalid_prob)

    @pytest.mark.parametrize("invalid_odds", [1.00, 0.95, 0.0, -1.50])
    def test_invalid_decimal_odds_raise(self, invalid_odds: float):
        with pytest.raises(ValueError, match="Decimal odds must be strictly greater than 1.0"):
            EVEngine.calculate(decimal_odds=invalid_odds, p_market_fair=0.55)

    def test_negative_bankroll_raises(self):
        with pytest.raises(ValueError, match="Bankroll cannot be negative"):
            EVEngine.calculate(decimal_odds=2.00, p_market_fair=0.55, bankroll=-500.0)

    def test_negative_or_all_zero_weights_raise(self):
        with pytest.raises(ValueError, match="Weights must be non-negative"):
            EVEngine.calculate(decimal_odds=2.00, p_market_fair=0.55, w_market=-1.0)
        with pytest.raises(ValueError, match="Total weights must be positive"):
            EVEngine.calculate(
                decimal_odds=2.00,
                p_market_fair=0.55,
                p_model_fair=0.55,
                w_market=0.0,
                w_model=0.0,
            )


# ==============================================================================
# Tier 7: Integration Bridges & Conformance
# ==============================================================================

class TestIntegrationAndConvenienceMethods:
    """Test suite for integration bridges with DevigResult, DistributionResult, and EVResult schema."""

    def test_devig_result_direct_bridge(self):
        """Verify seamless pipeline from DevigResult to EVEngine."""
        devig_res = DevigEngine.devig([1.80, 2.10], DevigMethod.SHIN)
        fair_prob = devig_res.fair_implied_probs[0]  # Favorite

        # Target sportsbook offers +100 (2.0) on favorite
        ev_res = from_devig_and_distribution(
            bet365_odds=2.00,
            devig_result=devig_res,
            outcome_index=0,
        )
        assert ev_res.market_implied_ev is not None
        assert ev_res.blended_ev > 0
        assert ev_res.is_positive_ev is True

    def test_distribution_result_direct_bridge(self):
        """Verify seamless pipeline from DistributionResult to EVEngine."""
        dist_res = DistributionEngine.evaluate_continuous_prop(
            projection_mean=65.0,
            line=65.0,
            position="WR",
            stat_category="rec_yds",
        )
        # Line 65.0 integer has push prob ~0.0116
        ev_res = from_devig_and_distribution(
            bet365_odds=1.909091,
            distribution_result=dist_res,
            is_over=True,
        )
        assert ev_res.model_implied_ev is not None
        assert ev_res.prob_push == dist_res.prob_push

    def test_american_odds_direct_input(self):
        """Verify direct evaluation from American odds integer (-110, +150)."""
        res_am = EVEngine.calculate_ev_from_american(
            bet365_american=-110,
            market_fair_prob=0.55,
        )
        res_dec = EVEngine.calculate(
            decimal_odds=1.909091,
            p_market_fair=0.55,
        )
        assert res_am.blended_ev == pytest.approx(res_dec.blended_ev, abs=1e-2)

    def test_pydantic_schema_compliance(self):
        """Ensure EVResult validates against app.schemas.ev.EVResult without data loss."""
        ev_res = EVEngine.calculate(decimal_odds=2.00, p_market_fair=0.55)
        schema_obj = SchemaEVResult.model_validate(ev_res.to_dict())
        assert schema_obj.blended_ev == ev_res.blended_ev
        assert schema_obj.recommended_stake == ev_res.recommended_stake

    def test_kelly_config_aliases_and_properties(self):
        """Verify KellyConfig accepts both standard names and aliases seamlessly."""
        cfg = KellyConfig(
            bankroll=5000.0,
            kelly_fraction=0.50,
            max_bankroll_pct=0.10,
            weight_market=0.70,
            weight_model=0.30,
            min_stake=10.0,
            max_absolute_stake=500.0,
        )
        assert cfg.fraction == 0.50
        assert cfg.kelly_fraction == 0.50
        assert cfg.max_allocation_pct == 0.10
        assert cfg.max_bankroll_pct == 0.10
        assert cfg.w_market == 0.70
        assert cfg.weight_market == 0.70
        assert cfg.w_model == 0.30
        assert cfg.weight_model == 0.30
        assert cfg.max_stake == 500.0
        assert cfg.max_absolute_stake == 500.0

        res = EVEngine.calculate_from_config(bet365_decimal=2.00, market_fair_prob=0.55, config=cfg)
        assert res.bankroll == 5000.0
        assert res.recommended_stake == 250.0  # 5000 * (0.10 * 0.50) = 250.0

    def test_under_prop_distribution_adapter(self):
        """Verify from_devig_and_distribution correctly handles is_over=False."""
        dist_res = DistributionEngine.evaluate_continuous_prop(
            projection_mean=60.0,
            line=65.0,
            position="WR",
            stat_category="rec_yds",
        )
        ev_res = from_devig_and_distribution(
            bet365_odds=1.909091,
            distribution_result=dist_res,
            is_over=False,
        )
        assert ev_res.model_implied_ev is not None
        assert ev_res.blended_ev > 0

    def test_calculate_stake_standalone_helper(self):
        """Verify standalone calculate_stake helper returns (stake, is_capped)."""
        stake, is_capped = calculate_stake(bankroll=1000.0, kelly_fraction=0.025, max_allocation_pct=0.05, min_stake=5.0)
        assert stake == 25.00
        assert is_capped is False

        stake_capped, is_capped_flag = calculate_stake(bankroll=1000.0, kelly_fraction=0.10, max_allocation_pct=0.05, min_stake=5.0)
        assert stake_capped == 50.00
        assert is_capped_flag is True

    def test_eighth_kelly_properties(self):
        """Verify eighth Kelly fraction and stake properties on EVResult."""
        res = EVEngine.calculate(decimal_odds=2.00, p_market_fair=0.60, bankroll=10000.0)
        # f* = 0.20 -> Quarter Kelly = 0.05 -> Eighth Kelly = 0.025 -> $250.00
        assert res.quarter_kelly_fraction == pytest.approx(0.050, abs=1e-4)
        assert res.eighth_kelly_fraction == pytest.approx(0.025, abs=1e-4)
        assert res.eighth_kelly_stake == pytest.approx(250.00, abs=0.01)

    def test_performance_benchmark_10k_ops(self):
        """Verify 10,000 EV & Kelly operations complete in under 500ms (<50 microseconds per op)."""
        start = time.perf_counter()
        for _ in range(10000):
            EVEngine.calculate(
                decimal_odds=1.909091,
                p_market_fair=0.53,
                p_model_fair=0.51,
                p_push=0.08,
                bankroll=5000.0,
            )
        elapsed_ms = (time.perf_counter() - start) * 1000.0
        assert elapsed_ms < 500.0, f"Performance too slow: {elapsed_ms:.2f}ms for 10k ops"
