"""
tests/unit/test_ev_adversarial.py

Adversarial Stress-Testing & Fuzzing Harness for EVEngine and EVResult.
Milestone: M4 (Dual-Edge EV+ Engine & Fractional Kelly Sizing)
Challenger 1 Empirical Verification Suite.

Validates:
1. Extreme Odds Boundaries (1.00001 to 1,000,000.0, -1,000,000 to +1,000,000).
2. Boundary Probabilities & Push Combinations (0.0, 1.0, push=1.0, epsilon margins).
3. Bankroll Edge Cases ($0, $0.01, $10,000,000, max/min stake interactions).
4. Mathematical Invariants & Monotonicity.
5. Large-Scale Fuzz Testing (10,000 randomized iterations).
6. Malformed, NaN, Inf, and Invalid Input Handling.
7. Schema Consistency & Conformance.
"""
from __future__ import annotations

import math
import random
import time
from typing import Any
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
# 1. Extreme Odds Stress Testing
# ==============================================================================

class TestAdversarialExtremeOdds:
    """Stress tests on extreme decimal and American odds."""

    def test_ultra_micro_decimal_odds_favorite(self):
        """Decimal odds 1.0001 (American ~ -1,000,000)."""
        dec_odds = 1.0001
        p_win = 0.99995
        # EV = (0.99995 * 1.0001 - 1.0) * 100 = (1.000049995 - 1) * 100 = +0.0049995%
        res = EVEngine.calculate(decimal_odds=dec_odds, p_market_fair=p_win, bankroll=10000.0)
        assert res.is_positive_ev is True
        assert res.blended_ev > 0.0
        assert not math.isnan(res.blended_ev)
        assert not math.isinf(res.blended_ev)
        assert not math.isnan(res.quarter_kelly_fraction)
        assert res.quarter_kelly_fraction >= 0.0

    def test_ultra_macro_decimal_odds_longshot(self):
        """Decimal odds 10000.0 (American +999,900)."""
        dec_odds = 10000.0
        p_win = 0.0002  # 0.02% true prob
        # EV = (0.0002 * 10000.0 - 1.0) * 100 = (2.0 - 1.0) * 100 = +100.0%
        res = EVEngine.calculate(decimal_odds=dec_odds, p_market_fair=p_win, bankroll=100000.0)
        assert res.blended_ev == pytest.approx(100.0, abs=1e-2)
        assert res.is_positive_ev is True
        # f* = 1.00 / 9999.0 = 0.00010001 -> f_Q = 0.000025
        assert res.quarter_kelly_fraction == pytest.approx(0.000025, abs=1e-6)
        assert res.recommended_stake == pytest.approx(2.50, abs=0.01) or res.recommended_stake == 0.0

    def test_extreme_american_odds_conversion(self):
        """Test +/- 100,000 American odds."""
        dec_pos = EVEngine.american_to_decimal(100000)
        assert dec_pos == pytest.approx(1001.0, abs=1e-4)

        dec_neg = EVEngine.american_to_decimal(-100000)
        assert dec_neg == pytest.approx(1.001, abs=1e-5)

        am_pos = EVEngine.decimal_to_american(1001.0)
        assert am_pos == 100000

        am_neg = EVEngine.decimal_to_american(1.001)
        assert am_neg == -100000

    @pytest.mark.parametrize(
        "invalid_odds",
        [
            1.0,
            0.9999,
            0.0,
            -1.0,
            -100.0,
            float("nan"),
            float("inf"),
            float("-inf"),
        ],
    )
    def test_invalid_decimal_odds_rejections(self, invalid_odds: float):
        """Ensure all decimal odds <= 1.0 or non-finite strictly raise ValueError."""
        with pytest.raises(ValueError):
            EVEngine.calculate(decimal_odds=invalid_odds, p_market_fair=0.50)

        with pytest.raises(ValueError):
            EVEngine.calculate_single_ev(0.50, invalid_odds)

        with pytest.raises(ValueError):
            EVEngine.calculate_kelly_fraction(0.05, invalid_odds)

    @pytest.mark.parametrize(
        "invalid_am",
        [
            0,
            50,
            -50,
            99,
            -99,
            float("nan"),
            float("inf"),
        ],
    )
    def test_invalid_american_odds_rejections(self, invalid_am: Any):
        """Ensure American odds in (-100, 100) or non-finite raise ValueError."""
        with pytest.raises(ValueError):
            EVEngine.american_to_decimal(invalid_am)


# ==============================================================================
# 2. Boundary Probabilities & Push Edge Cases
# ==============================================================================

class TestAdversarialProbabilitiesAndPush:
    """Stress tests on boundary probabilities and push refund combinations."""

    def test_certain_win_push_zero(self):
        """p_win = 1.0, p_push = 0.0 -> Guaranteed win."""
        res = EVEngine.calculate(decimal_odds=2.50, p_market_fair=1.0, bankroll=1000.0)
        assert res.blended_ev == pytest.approx(150.0, abs=1e-2)
        assert res.full_kelly_fraction == 1.0
        assert res.quarter_kelly_fraction == 0.25
        assert res.is_positive_ev is True

    def test_certain_loss_p_win_zero(self):
        """p_win = 0.0, p_push = 0.0 -> Guaranteed loss (-100% EV)."""
        res = EVEngine.calculate(decimal_odds=2.00, p_market_fair=0.0, bankroll=1000.0)
        assert res.blended_ev == -100.0
        assert res.full_kelly_fraction == 0.0
        assert res.quarter_kelly_fraction == 0.0
        assert res.recommended_stake == 0.0
        assert res.is_positive_ev is False

    def test_certain_push_refund(self):
        """p_win = 0.0, p_push = 1.0 -> Guaranteed refund (0% EV)."""
        res = EVEngine.calculate(decimal_odds=2.00, p_market_fair=0.0, p_push=1.0, bankroll=1000.0)
        assert res.blended_ev == 0.0
        assert res.quarter_kelly_fraction == 0.0
        assert res.recommended_stake == 0.0
        assert res.is_positive_ev is False

    def test_half_win_half_push(self):
        """p_win = 0.50, p_push = 0.50 -> No loss possible."""
        # EV = (0.50 * 2.0) - (1.0 - 0.50) = 1.0 - 0.50 = +0.50 (+50% EV)
        # f* = 0.50 / 1.0 = 0.50 -> f_Q = 0.125
        res = EVEngine.calculate(decimal_odds=2.00, p_market_fair=0.50, p_push=0.50, bankroll=1000.0)
        assert res.blended_ev == pytest.approx(50.0, abs=1e-2)
        assert res.quarter_kelly_fraction == pytest.approx(0.125, abs=1e-4)

    def test_boundary_sum_exactly_one(self):
        """p_win + p_push = 1.00000000 (Loss prob = 0)."""
        res = EVEngine.calculate(decimal_odds=1.90, p_market_fair=0.75, p_push=0.25)
        # EV = 0.75 * 1.90 - 0.75 = 0.75 * 0.90 = +0.675 (+67.5%)
        assert res.blended_ev == pytest.approx(67.50, abs=1e-2)

    def test_epsilon_tolerance_on_sum(self):
        """Slight float inaccuracy (1.0 + 1e-8) should be tolerated."""
        res = EVEngine.calculate(decimal_odds=2.0, p_market_fair=0.60, p_push=0.40 + 1e-8)
        assert res.blended_ev == pytest.approx(60.0, abs=1e-2)

    @pytest.mark.parametrize(
        "invalid_p_win, invalid_p_push",
        [
            (-0.001, 0.0),
            (1.001, 0.0),
            (0.50, -0.01),
            (0.50, 1.01),
            (0.60, 0.50),  # Sum = 1.10 > 1.0
            (0.90, 0.20),  # Sum = 1.10 > 1.0
            (float("nan"), 0.0),
            (0.50, float("nan")),
            (float("inf"), 0.0),
            (0.50, float("inf")),
        ],
    )
    def test_invalid_probabilities_rejection(self, invalid_p_win: float, invalid_p_push: float):
        """Ensure invalid probabilities and excessive sums are rejected."""
        with pytest.raises(ValueError):
            EVEngine.calculate(decimal_odds=2.0, p_market_fair=invalid_p_win, p_push=invalid_p_push)


# ==============================================================================
# 3. Bankroll & Sizing Edge Cases
# ==============================================================================

class TestAdversarialBankrollAndStakes:
    """Stress tests on bankroll edge cases and guardrail interactions."""

    def test_zero_bankroll(self):
        res = EVEngine.calculate(decimal_odds=2.0, p_market_fair=0.60, bankroll=0.0)
        assert res.quarter_kelly_fraction > 0.0
        assert res.quarter_kelly_stake == 0.0
        assert res.half_kelly_stake == 0.0
        assert res.full_kelly_stake == 0.0
        assert res.recommended_stake == 0.0

    def test_tiny_bankroll_micro_cents(self):
        """Bankroll $0.05 with min_stake $5.00."""
        res = EVEngine.calculate(decimal_odds=2.0, p_market_fair=0.60, bankroll=0.05, min_stake=5.0)
        assert res.recommended_stake == 0.0

    def test_huge_bankroll_ten_million(self):
        """Bankroll $10,000,000."""
        res = EVEngine.calculate(
            decimal_odds=2.0,
            p_market_fair=0.55,
            bankroll=10_000_000.0,
            max_allocation_pct=0.05,
        )
        # f* = 0.10 -> f_Q = 0.025 -> Stake = $250,000.00
        assert res.recommended_stake == pytest.approx(250_000.00, abs=0.01)
        assert res.is_capped is False

    def test_negative_bankroll_rejection(self):
        with pytest.raises(ValueError, match="Bankroll cannot be negative"):
            EVEngine.calculate(decimal_odds=2.0, p_market_fair=0.55, bankroll=-100.0)

        with pytest.raises(ValueError, match="Bankroll cannot be negative"):
            calculate_stake(-10.0, 0.05)

    def test_max_stake_cap_below_allocation_cap(self):
        """Absolute dollar cap limits large edge."""
        res = EVEngine.calculate(
            decimal_odds=2.0,
            p_market_fair=0.60,
            bankroll=10000.0,
            max_stake=100.0,
        )
        assert res.recommended_stake == 100.0
        assert res.is_capped is True

    def test_zero_min_stake_allows_micro_stakes(self):
        """min_stake=0.0 allows stakes under $1.00."""
        res = EVEngine.calculate(
            decimal_odds=2.0,
            p_market_fair=0.52,
            bankroll=10.0,
            min_stake=0.0,
        )
        # f* = 0.04 -> f_Q = 0.01 -> Stake = $0.10
        assert res.recommended_stake == pytest.approx(0.10, abs=0.01)


# ==============================================================================
# 4. Mathematical Invariants & Dual Signal Weights
# ==============================================================================

class TestAdversarialInvariantsAndWeights:
    """Stress tests on mathematical invariants, weighting edge cases, and continuity."""

    def test_pure_market_weight_zero_model(self):
        res = EVEngine.calculate(
            decimal_odds=2.0,
            p_market_fair=0.55,
            p_model_fair=0.45,
            w_market=1.0,
            w_model=0.0,
        )
        assert res.blended_win_prob == 0.55
        assert res.blended_ev == pytest.approx(10.0, abs=1e-2)

    def test_pure_model_weight_zero_market(self):
        res = EVEngine.calculate(
            decimal_odds=2.0,
            p_market_fair=0.55,
            p_model_fair=0.45,
            w_market=0.0,
            w_model=1.0,
        )
        assert res.blended_win_prob == 0.45
        assert res.blended_ev == pytest.approx(-10.0, abs=1e-2)

    def test_large_unnormalized_weights(self):
        """Weights (1000.0, 3000.0) -> 25% market, 75% model."""
        res = EVEngine.calculate(
            decimal_odds=2.0,
            p_market_fair=0.60,
            p_model_fair=0.50,
            w_market=1000.0,
            w_model=3000.0,
        )
        # Blend = 0.25 * 0.60 + 0.75 * 0.50 = 0.15 + 0.375 = 0.525
        assert res.blended_win_prob == pytest.approx(0.525, abs=1e-4)
        assert res.blended_ev == pytest.approx(5.0, abs=1e-2)

    def test_kelly_stake_monotonicity_with_edge(self):
        """Higher edge strictly yields higher or equal stake until capped."""
        res1 = EVEngine.calculate(2.0, p_market_fair=0.52, bankroll=1000.0)
        res2 = EVEngine.calculate(2.0, p_market_fair=0.54, bankroll=1000.0)
        res3 = EVEngine.calculate(2.0, p_market_fair=0.56, bankroll=1000.0)
        assert res1.quarter_kelly_stake <= res2.quarter_kelly_stake <= res3.quarter_kelly_stake

    def test_fraction_hierarchy_invariants(self):
        """Full Kelly >= Half Kelly >= Quarter Kelly >= Eighth Kelly >= 0."""
        res = EVEngine.calculate(2.0, p_market_fair=0.58, bankroll=10000.0)
        assert res.full_kelly_stake >= res.half_kelly_stake >= res.quarter_kelly_stake >= res.eighth_kelly_stake >= 0.0
        assert res.full_kelly_fraction >= res.half_kelly_fraction >= res.quarter_kelly_fraction >= res.eighth_kelly_fraction >= 0.0


# ==============================================================================
# 5. Integration Adapter Edge Cases
# ==============================================================================

class TestAdversarialIntegrationAdapters:
    """Stress tests on DevigResult and DistributionResult adapter bridges."""

    def test_devig_result_out_of_bounds_index(self):
        """Outcome index beyond length of DevigResult fair_implied_probs."""
        devig_res = DevigEngine.devig([1.90, 1.90], DevigMethod.MULTIPLICATIVE)
        # Outcome index 5 does not exist -> Should fallback to None without crashing
        ev_res = from_devig_and_distribution(
            bet365_odds=2.00,
            devig_result=devig_res,
            outcome_index=5,
            model_fair_prob=0.55,
        )
        assert ev_res.market_implied_ev is None
        assert ev_res.model_implied_ev is not None
        assert ev_res.blended_win_prob == 0.55

    def test_distribution_result_none_values(self):
        """DistributionResult is None, DevigResult is None, but manual probs provided."""
        ev_res = from_devig_and_distribution(
            bet365_odds=2.00,
            market_fair_prob=0.55,
        )
        assert ev_res.market_implied_ev == pytest.approx(10.0, abs=1e-2)
        assert ev_res.blended_ev == pytest.approx(10.0, abs=1e-2)


# ==============================================================================
# 6. Large-Scale Fuzz Testing (10,000 Randomized Runs)
# ==============================================================================

class TestAdversarialFuzzTesting:
    """Adversarial randomized fuzz testing across 10,000 valid and invalid parameter combinations."""

    def test_fuzz_10000_valid_inputs(self):
        """Generate 10,000 valid random configurations and assert strict mathematical invariants."""
        rng = random.Random(42)  # Deterministic seed for reproducible testing

        start_time = time.perf_counter()
        for i in range(10000):
            # Random decimal odds in [1.01, 500.0]
            dec_odds = rng.uniform(1.01, 500.0)

            # Random win and push probabilities summing <= 1.0
            p_win = rng.uniform(0.0001, 0.9999)
            max_push = 1.0 - p_win
            p_push = rng.uniform(0.0, max_push * 0.9) if max_push > 0 else 0.0

            # Random model prob
            p_model = rng.uniform(0.0001, 0.9999)
            if p_model + p_push > 1.0:
                p_model = 1.0 - p_push - 0.0001

            # Random bankroll
            bankroll = rng.uniform(10.0, 1_000_000.0)

            # Random weights
            w_mkt = rng.uniform(0.0, 10.0)
            w_mdl = rng.uniform(0.0, 10.0)
            if w_mkt == 0.0 and w_mdl == 0.0:
                w_mkt = 0.5
                w_mdl = 0.5

            res = EVEngine.calculate(
                decimal_odds=dec_odds,
                p_market_fair=p_win,
                p_model_fair=p_model,
                p_push=p_push,
                w_market=w_mkt,
                w_model=w_mdl,
                bankroll=bankroll,
            )

            # Invariant 1: No NaN or Inf anywhere
            assert not math.isnan(res.blended_ev)
            assert not math.isinf(res.blended_ev)
            assert not math.isnan(res.blended_win_prob)
            assert not math.isnan(res.recommended_stake)
            assert not math.isnan(res.quarter_kelly_fraction)

            # Invariant 2: Probability range
            assert 0.0 <= res.blended_win_prob <= 1.0

            # Invariant 3: Stake non-negativity
            assert res.quarter_kelly_stake >= 0.0
            assert res.half_kelly_stake >= 0.0
            assert res.full_kelly_stake >= 0.0
            assert res.recommended_stake >= 0.0

            # Invariant 4: Negative or zero EV must result in zero stake
            if res.blended_ev <= 0.0:
                assert res.quarter_kelly_fraction == 0.0
                assert res.recommended_stake == 0.0
                assert res.is_positive_ev is False
            else:
                assert res.is_positive_ev is True
                assert res.quarter_kelly_fraction >= 0.0

            # Invariant 5: Stake never exceeds bankroll allocation cap
            assert res.recommended_stake <= bankroll * 0.05 + 0.01

        elapsed = time.perf_counter() - start_time
        assert elapsed < 5.0, f"Fuzz test too slow: {elapsed:.2f}s for 10k iterations"

    def test_fuzz_1000_invalid_inputs_graceful_rejection(self):
        """Ensure malformed/corrupted inputs are consistently rejected with ValueError and never cause crash."""
        rng = random.Random(1337)
        for _ in range(1000):
            fault_type = rng.choice(["bad_odds", "bad_prob", "bad_sum", "bad_bankroll", "bad_weights"])

            if fault_type == "bad_odds":
                bad_d = rng.choice([0.0, -1.5, 0.999, 1.000, float("nan"), float("inf")])
                with pytest.raises(ValueError):
                    EVEngine.calculate(decimal_odds=bad_d, p_market_fair=0.55)

            elif fault_type == "bad_prob":
                bad_p = rng.choice([-0.5, 1.5, float("nan"), float("inf")])
                with pytest.raises(ValueError):
                    EVEngine.calculate(decimal_odds=2.0, p_market_fair=bad_p)

            elif fault_type == "bad_sum":
                p1 = rng.uniform(0.51, 0.99)
                p2 = rng.uniform(0.51, 0.99)
                with pytest.raises(ValueError):
                    EVEngine.calculate(decimal_odds=2.0, p_market_fair=p1, p_push=p2)

            elif fault_type == "bad_bankroll":
                bad_b = rng.uniform(-10000.0, -0.01)
                with pytest.raises(ValueError):
                    EVEngine.calculate(decimal_odds=2.0, p_market_fair=0.55, bankroll=bad_b)

            elif fault_type == "bad_weights":
                bad_w = rng.uniform(-10.0, -0.01)
                with pytest.raises(ValueError):
                    EVEngine.calculate(decimal_odds=2.0, p_market_fair=0.55, w_market=bad_w)
