"""
app/core/ev.py

Dual-Edge Expected Value (+EV) Engine & Fractional Kelly Bet Sizing.
Calculates Market-Implied EV, Model-Implied EV, Blended Consensus EV with push adjustments,
and computes risk-managed Fractional Kelly bet sizes and safety caps.
"""
from __future__ import annotations

import math
from enum import Enum
from typing import Any, Sequence
from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.core.devig import american_to_decimal, decimal_to_american


class KellySizingMode(str, Enum):
    """Supported Fractional Kelly bet sizing modes."""
    FULL = "full"
    HALF = "half"
    QUARTER = "quarter"
    EIGHTH = "eighth"
    CUSTOM = "custom"


class KellyConfig(BaseModel):
    """
    Configuration parameters for Expected Value and Fractional Kelly bet sizing.
    """
    model_config = ConfigDict(populate_by_name=True, from_attributes=True, validate_assignment=True)

    bankroll: float = Field(default=1000.0, ge=0.0, description="Total bankroll in dollars")
    fraction: float = Field(default=0.25, gt=0.0, le=1.0, description="Fractional Kelly multiplier (default: 0.25 for Quarter Kelly)")
    max_allocation_pct: float = Field(default=0.05, gt=0.0, le=1.0, description="Maximum bankroll allocation percentage per bet (default: 5%)")
    min_stake: float = Field(default=5.0, ge=0.0, description="Minimum actionable bet floor in dollars")
    max_stake: float | None = Field(default=None, ge=0.0, description="Optional maximum absolute dollar stake cap")
    w_market: float = Field(default=0.60, ge=0.0, description="Weight assigned to market probability signal")
    w_model: float = Field(default=0.40, ge=0.0, description="Weight assigned to model probability signal")

    @model_validator(mode="before")
    @classmethod
    def handle_aliases(cls, data: Any) -> Any:
        if isinstance(data, dict):
            data = dict(data)
            if "kelly_fraction" in data and "fraction" not in data:
                data["fraction"] = data.pop("kelly_fraction")
            if "max_bankroll_pct" in data and "max_allocation_pct" not in data:
                data["max_allocation_pct"] = data.pop("max_bankroll_pct")
            if "weight_market" in data and "w_market" not in data:
                data["w_market"] = data.pop("weight_market")
            if "weight_model" in data and "w_model" not in data:
                data["w_model"] = data.pop("weight_model")
            if "max_absolute_stake" in data and "max_stake" not in data:
                data["max_stake"] = data.pop("max_absolute_stake")
        return data

    @property
    def kelly_fraction(self) -> float:
        return self.fraction

    @property
    def max_bankroll_pct(self) -> float:
        return self.max_allocation_pct

    @property
    def weight_market(self) -> float:
        return self.w_market

    @property
    def weight_model(self) -> float:
        return self.w_model

    @property
    def max_absolute_stake(self) -> float | None:
        return self.max_stake


class EVResult(BaseModel):
    """
    Pure mathematical container for EV calculations and Fractional Kelly bet sizing.
    All EV metrics are expressed as percentages (e.g. 5.25 for +5.25% EV).
    """
    model_config = ConfigDict(populate_by_name=True, from_attributes=True)

    market_implied_ev: float | None = Field(
        default=None,
        description="EV percentage against sharp devigged benchmark: [(P_mkt * D) - (1 - P_push)] * 100"
    )
    model_implied_ev: float | None = Field(
        default=None,
        description="EV percentage against statistical projection distribution: [(P_mdl * D) - (1 - P_push)] * 100"
    )
    blended_ev: float = Field(
        ...,
        description="Weighted consensus EV percentage: [(P_blend * D) - (1 - P_push)] * 100"
    )
    blended_win_prob: float = Field(
        ...,
        description="Weighted win probability in range [0.0, 1.0]"
    )
    prob_push: float = Field(
        default=0.0,
        description="Push refund probability for integer lines"
    )
    quarter_kelly_fraction: float = Field(
        ...,
        description="Quarter Kelly fraction: 0.25 * [ (P_win * D - (1 - P_push)) / (D - 1) ]"
    )
    quarter_kelly_stake: float = Field(
        ...,
        description="Recommended stake for Quarter Kelly based on bankroll and safety caps"
    )
    half_kelly_stake: float = Field(
        ...,
        description="Stake for Half Kelly sizing"
    )
    full_kelly_stake: float = Field(
        ...,
        description="Stake for Full Kelly sizing"
    )
    recommended_stake: float = Field(
        ...,
        description="Selected actionable stake (defaults to Quarter Kelly subject to min floor & caps)"
    )
    is_capped: bool = Field(
        default=False,
        description="True if recommended stake was truncated by allocation cap"
    )
    bankroll: float = Field(
        default=1000.0,
        description="Bankroll used for stake calculations"
    )

    # Computed Properties & Backward Compatibility Helpers
    @property
    def edge_pct(self) -> float:
        """Alias for blended_ev percentage."""
        return self.blended_ev

    @property
    def is_positive_ev(self) -> bool:
        """True if the blended consensus EV is strictly positive."""
        return self.blended_ev > 0.0

    @property
    def ev_decimal(self) -> float:
        """Blended EV expressed as decimal fraction (e.g. 0.0525 for 5.25%)."""
        return round(self.blended_ev / 100.0, 6)

    @property
    def full_kelly_fraction(self) -> float:
        """Full Kelly bankroll fraction."""
        return round(self.quarter_kelly_fraction * 4.0, 6) if self.quarter_kelly_fraction > 0 else 0.0

    @property
    def half_kelly_fraction(self) -> float:
        """Half Kelly bankroll fraction."""
        return round(self.quarter_kelly_fraction * 2.0, 6) if self.quarter_kelly_fraction > 0 else 0.0

    @property
    def eighth_kelly_fraction(self) -> float:
        """Eighth Kelly bankroll fraction."""
        return round(self.quarter_kelly_fraction * 0.5, 6) if self.quarter_kelly_fraction > 0 else 0.0

    @property
    def eighth_kelly_stake(self) -> float:
        """Actionable Eighth Kelly stake."""
        if self.quarter_kelly_fraction <= 0.0 or self.bankroll <= 0.0:
            return 0.0
        raw = self.bankroll * self.eighth_kelly_fraction
        return round(raw, 2)

    def to_dict(self) -> dict[str, Any]:
        """Serialize result to dictionary."""
        return self.model_dump()


class EVEngine:
    """
    Quantitative Expected Value (+EV) and Fractional Kelly Bet Sizing Engine.
    Provides mathematical calculation methods and domain adapter integrations.
    """

    @staticmethod
    def american_to_decimal(american_odds: int | float) -> float:
        """Convert American odds to Decimal odds."""
        return american_to_decimal(american_odds)

    @staticmethod
    def decimal_to_american(decimal_odds: float) -> int:
        """Convert Decimal odds to American integer odds."""
        return decimal_to_american(decimal_odds)

    @staticmethod
    def calculate_single_ev(
        p_win: float,
        decimal_odds: float,
        p_push: float = 0.0,
    ) -> float:
        """
        Calculate single push-adjusted Expected Value (EV) as a decimal fraction.

        Formula:
            EV_decimal = (p_win * Decimal_Odds) - (1.0 - p_push)

        Args:
            p_win: Probability of winning in [0.0, 1.0].
            decimal_odds: Target Decimal odds strictly > 1.0.
            p_push: Probability of push/refund on integer line in [0.0, 1.0].

        Returns:
            float: Expected Value as decimal fraction (e.g. 0.0525 for +5.25% EV).

        Raises:
            ValueError: If decimal odds <= 1.0 or probabilities not in [0.0, 1.0] or sum > 1.0.
        """
        if not isinstance(decimal_odds, (int, float)) or math.isnan(decimal_odds) or math.isinf(decimal_odds) or decimal_odds <= 1.0:
            raise ValueError(f"Decimal odds must be strictly greater than 1.0, got {decimal_odds}")

        if not isinstance(p_win, (int, float)) or math.isnan(p_win) or math.isinf(p_win) or p_win < 0.0 or p_win > 1.0:
            raise ValueError(f"Probabilities must be between 0.0 and 1.0, got win prob {p_win}")

        if not isinstance(p_push, (int, float)) or math.isnan(p_push) or math.isinf(p_push) or p_push < 0.0 or p_push > 1.0:
            raise ValueError(f"Probabilities must be between 0.0 and 1.0, got push prob {p_push}")

        if p_win + p_push > 1.0 + 1e-7:
            raise ValueError(f"Sum of win and push probabilities cannot exceed 1.0, got {p_win + p_push}")

        return (p_win * decimal_odds) - (1.0 - p_push)

    @classmethod
    def blend_probabilities(
        cls,
        p_market: float | None,
        p_model: float | None,
        w_market: float = 0.60,
        w_model: float = 0.40,
    ) -> float:
        """
        Compute weighted convex combination of market and model win probabilities.
        Gracefully handles single-signal presence and unnormalized weights.

        Args:
            p_market: Vig-free market probability from benchmark devig (or None).
            p_model: Model probability from statistical distribution (or None).
            w_market: Non-negative weight for market signal.
            w_model: Non-negative weight for model signal.

        Returns:
            float: Blended win probability in [0.0, 1.0].

        Raises:
            ValueError: If both signals are None or weights are negative.
        """
        if p_market is None and p_model is None:
            raise ValueError("At least one probability signal must be provided.")

        if w_market < 0.0 or w_model < 0.0:
            raise ValueError("Weights must be non-negative.")

        for p_name, p_val in [("p_market", p_market), ("p_model", p_model)]:
            if p_val is not None:
                if not isinstance(p_val, (int, float)) or math.isnan(p_val) or math.isinf(p_val) or p_val < 0.0 or p_val > 1.0:
                    raise ValueError(f"Probabilities must be between 0.0 and 1.0, got {p_name}={p_val}")

        if p_market is not None and p_model is not None:
            total_w = w_market + w_model
            if total_w <= 0.0:
                return round(0.50 * p_market + 0.50 * p_model, 6)
            return round(((w_market * p_market) + (w_model * p_model)) / total_w, 6)
        elif p_market is not None:
            return round(float(p_market), 6)
        else:
            assert p_model is not None
            return round(float(p_model), 6)

    @classmethod
    def calculate_kelly_fraction(
        cls,
        ev_decimal: float,
        decimal_odds: float,
        fraction: float = 1.0,
    ) -> float:
        """
        Calculate Fractional Kelly bankroll fraction.

        Formula:
            f* = max(0.0, EV_decimal / (Decimal_Odds - 1.0)) * fraction

        Args:
            ev_decimal: Expected value as a decimal fraction.
            decimal_odds: Target decimal odds (> 1.0).
            fraction: Kelly scaling multiplier (e.g. 0.25 for Quarter Kelly).

        Returns:
            float: Kelly bankroll fraction.
        """
        if not isinstance(decimal_odds, (int, float)) or math.isnan(decimal_odds) or math.isinf(decimal_odds) or decimal_odds <= 1.0:
            raise ValueError(f"Decimal odds must be strictly greater than 1.0, got {decimal_odds}")

        if fraction < 0.0:
            raise ValueError(f"Kelly fraction multiplier must be non-negative, got {fraction}")

        if ev_decimal <= 0.0 or math.isnan(ev_decimal):
            return 0.0

        b_odds = decimal_odds - 1.0
        full_f = ev_decimal / b_odds
        return round(max(0.0, full_f * fraction), 6)

    @classmethod
    def calculate_stake(
        cls,
        bankroll: float,
        kelly_fraction: float,
        max_allocation_pct: float = 0.05,
        min_stake: float = 5.0,
        max_stake: float | None = None,
    ) -> tuple[float, bool]:
        """
        Calculate dollar stake with bankroll allocation caps and minimum bet floor.

        Args:
            bankroll: Total active bankroll in dollars (>= 0.0).
            kelly_fraction: Bankroll fraction (>= 0.0).
            max_allocation_pct: Maximum bankroll allocation percentage per wager.
            min_stake: Minimum bet threshold in dollars.
            max_stake: Optional maximum absolute dollar ceiling.

        Returns:
            tuple[float, bool]: (final_stake, is_capped)
        """
        if bankroll < 0.0:
            raise ValueError(f"Bankroll cannot be negative, got {bankroll}")

        if bankroll == 0.0 or kelly_fraction <= 0.0:
            return 0.0, False

        raw_stake = bankroll * kelly_fraction
        cap_limit = bankroll * max_allocation_pct
        if max_stake is not None and max_stake > 0.0:
            cap_limit = min(cap_limit, max_stake)

        is_capped = raw_stake > cap_limit

        if raw_stake < min_stake:
            return 0.0, is_capped

        final_stake = round(min(raw_stake, cap_limit), 2)
        return final_stake, is_capped

    @classmethod
    def calculate(
        cls,
        decimal_odds: float | None = None,
        american_odds: int | float | None = None,
        p_market_fair: float | None = None,
        p_model_fair: float | None = None,
        p_push: float = 0.0,
        config: KellyConfig | None = None,
        *,
        bet365_decimal: float | None = None,
        bet365_american: int | float | None = None,
        market_fair_prob: float | None = None,
        model_fair_prob: float | None = None,
        prob_push: float | None = None,
        weight_market: float | None = None,
        weight_model: float | None = None,
        w_market: float | None = None,
        w_model: float | None = None,
        bankroll: float | None = None,
        kelly_fraction: float | None = None,
        fraction: float | None = None,
        min_stake: float | None = None,
        max_bankroll_pct: float | None = None,
        max_allocation_pct: float | None = None,
        max_absolute_stake: float | None = None,
        max_stake: float | None = None,
    ) -> EVResult:
        """
        Comprehensive Dual-Edge Expected Value (+EV) calculation and Fractional Kelly sizing.

        Accepts standard parameters and convenient aliases.
        """
        # Resolve target decimal odds
        target_dec = decimal_odds if decimal_odds is not None else bet365_decimal
        target_am = american_odds if american_odds is not None else bet365_american

        if target_dec is not None:
            if not isinstance(target_dec, (int, float)) or math.isnan(target_dec) or math.isinf(target_dec) or target_dec <= 1.0:
                raise ValueError(f"Decimal odds must be strictly greater than 1.0, got {target_dec}")
            final_decimal = float(target_dec)
        elif target_am is not None:
            final_decimal = american_to_decimal(int(target_am))
        else:
            raise ValueError("Must provide decimal odds or American odds.")

        # Resolve probabilities
        p_mkt = p_market_fair if p_market_fair is not None else market_fair_prob
        p_mdl = p_model_fair if p_model_fair is not None else model_fair_prob
        push_p = prob_push if prob_push is not None else p_push

        if not isinstance(push_p, (int, float)) or math.isnan(push_p) or math.isinf(push_p) or push_p < 0.0 or push_p > 1.0:
            raise ValueError(f"Probabilities must be between 0.0 and 1.0, got push prob {push_p}")

        if p_mkt is None and p_mdl is None:
            raise ValueError("At least one probability signal must be provided.")

        for p_name, p_val in [("market_fair_prob", p_mkt), ("model_fair_prob", p_mdl)]:
            if p_val is not None:
                if not isinstance(p_val, (int, float)) or math.isnan(p_val) or math.isinf(p_val) or p_val < 0.0 or p_val > 1.0:
                    raise ValueError(f"Probabilities must be between 0.0 and 1.0, got {p_name}={p_val}")
                if p_val + push_p > 1.0 + 1e-7:
                    raise ValueError(f"Sum of win and push probabilities cannot exceed 1.0, got {p_val + push_p}")

        # Resolve configuration parameters
        cfg = config or KellyConfig()
        w_mkt_val = w_market if w_market is not None else (weight_market if weight_market is not None else cfg.w_market)
        w_mdl_val = w_model if w_model is not None else (weight_model if weight_model is not None else cfg.w_model)

        if w_mkt_val < 0.0 or w_mdl_val < 0.0:
            raise ValueError("Weights must be non-negative.")
        if p_mkt is not None and p_mdl is not None and (w_mkt_val + w_mdl_val) <= 0.0:
            raise ValueError("Total weights must be positive.")

        b_roll = bankroll if bankroll is not None else cfg.bankroll
        if b_roll < 0.0:
            raise ValueError("Bankroll cannot be negative.")

        k_frac = fraction if fraction is not None else (kelly_fraction if kelly_fraction is not None else cfg.fraction)
        m_stake = min_stake if min_stake is not None else cfg.min_stake
        max_alloc = max_allocation_pct if max_allocation_pct is not None else (max_bankroll_pct if max_bankroll_pct is not None else cfg.max_allocation_pct)
        max_s = max_stake if max_stake is not None else (max_absolute_stake if max_absolute_stake is not None else cfg.max_stake)

        # 1. Evaluate Individual Edge Signals
        mkt_ev_pct: float | None = None
        if p_mkt is not None:
            mkt_ev_raw = (p_mkt * final_decimal) - (1.0 - push_p)
            mkt_ev_pct = round(mkt_ev_raw * 100.0, 4)

        mdl_ev_pct: float | None = None
        if p_mdl is not None:
            mdl_ev_raw = (p_mdl * final_decimal) - (1.0 - push_p)
            mdl_ev_pct = round(mdl_ev_raw * 100.0, 4)

        # 2. Blend Probabilities & Calculate Blended EV
        blend_prob = cls.blend_probabilities(p_mkt, p_mdl, w_mkt_val, w_mdl_val)
        blended_ev_raw = (blend_prob * final_decimal) - (1.0 - push_p)
        blended_ev_pct = round(blended_ev_raw * 100.0, 4)

        # 3. Fractional Kelly Sizing & Guardrails
        if blended_ev_raw <= 0.0 or blend_prob <= 0.0:
            quarter_f = 0.0
            q_stake = 0.0
            h_stake = 0.0
            f_stake = 0.0
            rec_stake = 0.0
            is_capped = False
        else:
            b_odds = final_decimal - 1.0
            full_f = max(0.0, blended_ev_raw / b_odds)
            quarter_f = round(full_f * 0.25, 6)
            half_f = full_f * 0.50
            chosen_f = full_f * k_frac

            q_stake, _ = cls.calculate_stake(b_roll, quarter_f, max_alloc, m_stake, max_s)
            h_stake, _ = cls.calculate_stake(b_roll, half_f, max_alloc, m_stake, max_s)
            f_stake, _ = cls.calculate_stake(b_roll, full_f, max_alloc, m_stake, max_s)
            rec_stake, is_capped = cls.calculate_stake(b_roll, chosen_f, max_alloc, m_stake, max_s)

        return EVResult(
            market_implied_ev=mkt_ev_pct,
            model_implied_ev=mdl_ev_pct,
            blended_ev=blended_ev_pct,
            blended_win_prob=round(blend_prob, 6),
            prob_push=round(push_p, 6),
            quarter_kelly_fraction=quarter_f,
            quarter_kelly_stake=q_stake,
            half_kelly_stake=h_stake,
            full_kelly_stake=f_stake,
            recommended_stake=rec_stake,
            is_capped=is_capped,
            bankroll=b_roll,
        )

    @classmethod
    def from_devig_and_distribution(
        cls,
        bet365_odds: float | int,
        odds_type: str = "decimal",
        devig_result: Any | None = None,
        outcome_index: int = 0,
        distribution_result: Any | None = None,
        is_over: bool = True,
        config: KellyConfig | None = None,
        **kwargs: Any,
    ) -> EVResult:
        """
        High-level domain adapter linking DevigResult and DistributionResult directly into EVResult.
        """
        odds_type_lower = str(odds_type).lower().strip()
        if odds_type_lower == "american" or (isinstance(bet365_odds, int) and (bet365_odds <= -100 or bet365_odds >= 100)):
            decimal_odds = american_to_decimal(int(bet365_odds))
        else:
            decimal_odds = float(bet365_odds)

        market_fair_prob: float | None = kwargs.pop("market_fair_prob", kwargs.pop("p_market_fair", None))
        if market_fair_prob is None and devig_result is not None:
            probs = getattr(devig_result, "fair_implied_probs", None) or getattr(devig_result, "fair_implied_probabilities", None)
            if probs and 0 <= outcome_index < len(probs):
                market_fair_prob = float(probs[outcome_index])

        model_fair_prob: float | None = kwargs.pop("model_fair_prob", kwargs.pop("p_model_fair", None))
        prob_push: float = kwargs.pop("prob_push", kwargs.pop("p_push", 0.0))
        if distribution_result is not None:
            prob_push = float(getattr(distribution_result, "prob_push", prob_push))
            if is_over:
                model_fair_prob = float(
                    getattr(distribution_result, "prob_over", getattr(distribution_result, "conditional_prob_over", model_fair_prob or 0.0))
                )
            else:
                model_fair_prob = float(
                    getattr(distribution_result, "prob_under", getattr(distribution_result, "conditional_prob_under", model_fair_prob or 0.0))
                )

        return cls.calculate(
            decimal_odds=decimal_odds,
            market_fair_prob=market_fair_prob,
            model_fair_prob=model_fair_prob,
            prob_push=prob_push,
            config=config,
            **kwargs,
        )

    @classmethod
    def calculate_ev(
        cls,
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        """
        Flexible calculation entrypoint.

        Usage forms:
        1. Single EV float calculation:
           EVEngine.calculate_ev(p_win=0.55, decimal_odds=2.0, p_push=0.0) -> float
           EVEngine.calculate_ev(0.55, 2.0, 0.0) -> float (where first arg is prob <= 1.0)
        2. Full EVResult calculation:
           EVEngine.calculate_ev(2.10, market_fair_prob=0.515, ...) -> EVResult
           EVEngine.calculate_ev(bet365_decimal=2.10, market_fair_prob=0.55, ...) -> EVResult
        """
        # If called with pure positional arguments (p_win <= 1.0, decimal_odds > 1.0, ...)
        if len(args) >= 2 and isinstance(args[0], (int, float)) and isinstance(args[1], (int, float)):
            first_val = float(args[0])
            second_val = float(args[1])
            # If first arg is probability (0.0 <= p <= 1.0) and second is decimal odds (> 1.0)
            if 0.0 <= first_val <= 1.0 and second_val > 1.0 and "market_fair_prob" not in kwargs and "model_fair_prob" not in kwargs and "p_market_fair" not in kwargs and "p_model_fair" not in kwargs:
                p_push = float(args[2]) if len(args) > 2 else kwargs.get("p_push", kwargs.get("prob_push", 0.0))
                return cls.calculate_single_ev(first_val, second_val, p_push)

        # If keyword arguments explicitly denote single EV calculation (p_win and decimal_odds given without market/model prob)
        if "p_win" in kwargs and "decimal_odds" in kwargs and "market_fair_prob" not in kwargs and "model_fair_prob" not in kwargs:
            return cls.calculate_single_ev(kwargs["p_win"], kwargs["decimal_odds"], kwargs.get("p_push", 0.0))

        # Otherwise, delegate to full calculation
        if len(args) == 1 and "decimal_odds" not in kwargs and "bet365_decimal" not in kwargs:
            kwargs["decimal_odds"] = args[0]
        elif len(args) > 1 and "decimal_odds" not in kwargs and "bet365_decimal" not in kwargs:
            kwargs["decimal_odds"] = args[0]
            if "market_fair_prob" not in kwargs and "p_market_fair" not in kwargs:
                kwargs["market_fair_prob"] = args[1]

        return cls.calculate(**kwargs)

    @classmethod
    def calculate_ev_from_american(
        cls,
        bet365_american: int | float,
        market_fair_prob: float | None = None,
        model_fair_prob: float | None = None,
        prob_push: float = 0.0,
        config: KellyConfig | None = None,
        **kwargs: Any,
    ) -> EVResult:
        """Calculate EV and Kelly stakes directly from American odds."""
        return cls.calculate(
            american_odds=bet365_american,
            market_fair_prob=market_fair_prob,
            model_fair_prob=model_fair_prob,
            prob_push=prob_push,
            config=config,
            **kwargs,
        )

    @classmethod
    def calculate_from_config(
        cls,
        bet365_decimal: float,
        market_fair_prob: float | None = None,
        model_fair_prob: float | None = None,
        prob_push: float = 0.0,
        config: KellyConfig | None = None,
    ) -> EVResult:
        """Ergonomic wrapper taking a KellyConfig instance."""
        return cls.calculate(
            decimal_odds=bet365_decimal,
            market_fair_prob=market_fair_prob,
            model_fair_prob=model_fair_prob,
            prob_push=prob_push,
            config=config,
        )

    @classmethod
    def from_devig_and_distribution(
        cls,
        bet365_odds: float | int,
        odds_type: str = "decimal",
        devig_result: Any | None = None,
        outcome_index: int = 0,
        distribution_result: Any | None = None,
        is_over: bool = True,
        config: KellyConfig | None = None,
        **kwargs: Any,
    ) -> EVResult:
        """
        High-level domain adapter linking DevigResult and DistributionResult directly into EVResult.
        """
        odds_type_lower = str(odds_type).lower().strip()
        if odds_type_lower == "american" or (isinstance(bet365_odds, int) and (bet365_odds <= -100 or bet365_odds >= 100)):
            decimal_odds = american_to_decimal(int(bet365_odds))
        else:
            decimal_odds = float(bet365_odds)

        market_fair_prob: float | None = kwargs.pop("market_fair_prob", kwargs.pop("p_market_fair", None))
        if market_fair_prob is None and devig_result is not None:
            probs = getattr(devig_result, "fair_implied_probs", None) or getattr(devig_result, "fair_implied_probabilities", None)
            if probs and 0 <= outcome_index < len(probs):
                market_fair_prob = float(probs[outcome_index])

        model_fair_prob: float | None = kwargs.pop("model_fair_prob", kwargs.pop("p_model_fair", None))
        prob_push: float = kwargs.pop("prob_push", kwargs.pop("p_push", 0.0))
        if distribution_result is not None:
            prob_push = float(getattr(distribution_result, "prob_push", prob_push))
            if is_over:
                model_fair_prob = float(
                    getattr(distribution_result, "prob_over", getattr(distribution_result, "conditional_prob_over", model_fair_prob or 0.0))
                )
            else:
                model_fair_prob = float(
                    getattr(distribution_result, "prob_under", getattr(distribution_result, "conditional_prob_under", model_fair_prob or 0.0))
                )

        return cls.calculate(
            decimal_odds=decimal_odds,
            market_fair_prob=market_fair_prob,
            model_fair_prob=model_fair_prob,
            prob_push=prob_push,
            config=config,
            **kwargs,
        )


# ==============================================================================
# Standalone Functional Exports for High-Performance Import Ergonomics
# ==============================================================================

def calculate_ev(
    *args: Any,
    **kwargs: Any,
) -> Any:
    """Convenience functional wrapper for EVEngine.calculate_ev."""
    return EVEngine.calculate_ev(*args, **kwargs)


def calculate_fractional_kelly(
    ev_decimal: float,
    decimal_odds: float,
    fraction: float = 1.0,
) -> float:
    """Convenience functional wrapper for EVEngine.calculate_kelly_fraction."""
    return EVEngine.calculate_kelly_fraction(ev_decimal, decimal_odds, fraction)


def blend_probabilities(
    p_market: float | None,
    p_model: float | None,
    w_market: float = 0.60,
    w_model: float = 0.40,
) -> float:
    """Convenience functional wrapper for EVEngine.blend_probabilities."""
    return EVEngine.blend_probabilities(p_market, p_model, w_market, w_model)


def calculate_stake(
    bankroll: float,
    kelly_fraction: float,
    max_allocation_pct: float = 0.05,
    min_stake: float = 5.0,
    max_stake: float | None = None,
) -> tuple[float, bool]:
    """Convenience functional wrapper for EVEngine.calculate_stake."""
    return EVEngine.calculate_stake(bankroll, kelly_fraction, max_allocation_pct, min_stake, max_stake)


def from_devig_and_distribution(
    bet365_odds: float | int,
    odds_type: str = "decimal",
    devig_result: Any | None = None,
    outcome_index: int = 0,
    distribution_result: Any | None = None,
    is_over: bool = True,
    config: KellyConfig | None = None,
    **kwargs: Any,
) -> EVResult:
    """Convenience functional wrapper for EVEngine.from_devig_and_distribution."""
    return EVEngine.from_devig_and_distribution(
        bet365_odds=bet365_odds,
        odds_type=odds_type,
        devig_result=devig_result,
        outcome_index=outcome_index,
        distribution_result=distribution_result,
        is_over=is_over,
        config=config,
        **kwargs,
    )
