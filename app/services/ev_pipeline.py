"""
app.services.ev_pipeline: Core pipeline orchestrator matching Odds with Devigging and Projections.
"""
from __future__ import annotations

import hashlib
import logging
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.core.devig import DevigEngine, DevigMethod
from app.core.distributions import DistributionEngine, DistributionType
from app.core.ev import EVEngine, KellyConfig
from app.core.normalizer import PlayerNameNormalizer, TeamNormalizer
from app.db.cache import AppSettings, cache
from app.schemas.ev import MatchedEVOpportunity, PropBreakdown
from app.schemas.odds import Event, MarketOffer, MarketOutcome, OutcomeType
from app.schemas.projections import PlayerProjection, Position, StatCategory

logger = logging.getLogger(__name__)

SUSPICIOUS_EV_THRESHOLD_PCT = 15.0

CV_MAP = {
    Position.QB: 0.30,
    Position.RB: 0.45,
    Position.WR: 0.50,
    Position.TE: 0.55,
}

MARKET_DISPLAY_NAMES = {
    "player_pass_yds": "Passing Yards",
    "player_pass_tds": "Passing Touchdowns",
    "player_pass_interceptions": "Pass Interceptions",
    "player_rush_yds": "Rushing Yards",
    "player_rec_yds": "Receiving Yards",
    "player_receptions": "Receptions",
    "player_anytime_td": "Anytime Touchdown",
    "totals": "Total Game Points",
    "spreads": "Point Spread",
    "h2h": "Moneyline",
}


class EVPipellineService:
    """
    High-performance pipeline coordinating Devigging, Statistical Modeling, and Kelly sizing.
    """

    @classmethod
    def generate_opportunity_id(
        cls,
        event_id: str,
        market_key: str,
        player_name: str | None,
        outcome_name: str,
        line: float | None,
    ) -> str:
        raw_key = f"{event_id}_{market_key}_{player_name or 'none'}_{outcome_name}_{line or '0'}".lower()
        return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()[:16]

    @classmethod
    def compute_chart_curve(
        cls,
        stat_category: StatCategory,
        mean_proj: float,
        line: float,
        position: Position = Position.WR,
    ) -> dict[str, Any] | None:
        """
        Generate Chart.js formatted (x, y) coordinates for PDF / PMF curves.
        """
        if mean_proj <= 0:
            return None

        labels: list[float] = []
        densities: list[float] = []

        is_discrete = stat_category in {
            StatCategory.PASSING_TDS,
            StatCategory.PASSING_INTERCEPTIONS,
            StatCategory.RUSHING_TDS,
            StatCategory.RECEIVING_TDS,
            StatCategory.RECEPTIONS,
            StatCategory.ANYTIME_TD,
        }

        if is_discrete:
            max_k = max(6, int(math.ceil(mean_proj * 3.5)))
            for k in range(0, max_k + 1):
                prob = (math.exp(-mean_proj) * (mean_proj ** k)) / math.factorial(k)
                labels.append(float(k))
                densities.append(round(prob, 4))
        else:
            cv = CV_MAP.get(position, 0.45)
            sigma = math.sqrt(math.log(1.0 + cv * cv))
            mu = math.log(mean_proj) - 0.5 * sigma * sigma

            start_x = max(0.5, mean_proj * 0.2)
            end_x = mean_proj * 2.4
            steps = 40
            dx = (end_x - start_x) / steps

            for i in range(steps + 1):
                x = start_x + i * dx
                pdf = (1.0 / (x * sigma * math.sqrt(2.0 * math.pi))) * math.exp(-((math.log(x) - mu) ** 2) / (2.0 * sigma * sigma))
                labels.append(round(x, 1))
                densities.append(round(pdf, 6))

        return {
            "labels": labels,
            "data": densities,
            "target_line": line,
            "mean_projection": mean_proj,
            "is_discrete": is_discrete,
        }

    @classmethod
    def process_data(
        cls,
        events: list[Event] | None = None,
        projections: list[PlayerProjection] | None = None,
        settings: AppSettings | None = None,
    ) -> list[MatchedEVOpportunity]:
        """
        Execute end-to-end matching, devigging, distribution modeling, and EV scoring.
        """
        cfg = settings or cache.get_settings()
        kelly_cfg = KellyConfig(
            bankroll=cfg.bankroll,
            fraction=cfg.kelly_fraction,
            w_market=cfg.w_market,
            w_model=cfg.w_model,
            min_stake=cfg.min_stake,
        )

        all_events = events if events is not None else cache.get_events()
        all_projs = projections if projections is not None else cache.get_projections()

        # Build quick projection lookup map
        # Build quick projection lookup map: player_name -> {stat_category: PlayerProjection}
        proj_lookup: dict[str, dict[StatCategory, PlayerProjection]] = {}
        for p in all_projs:
            clean = PlayerNameNormalizer.clean_name(p.canonical_name or p.player_name).lower()
            proj_lookup.setdefault(clean, {})[p.stat_category] = p

        matched_opportunities: list[MatchedEVOpportunity] = []

        for event in all_events:
            game_str = event.game_title
            commence_dt = event.commence_time or datetime.now(timezone.utc)

            # Group market offers by market_key + player_name + line
            market_groups: dict[str, dict[str, MarketOffer]] = {}
            for bm in event.bookmakers:
                bm_key = bm.key.lower()
                for offer in bm.markets:
                    p_name = offer.player_name or (offer.outcomes[0].description if offer.outcomes and offer.outcomes[0].description else "")
                    line_val = offer.point or (offer.outcomes[0].point if offer.outcomes else None)
                    group_key = f"{offer.market_key}_{p_name}_{line_val}".lower()
                    market_groups.setdefault(group_key, {})[bm_key] = offer

            for group_key, bms_offers in market_groups.items():
                # Target book (Bet365 preferred, else first bookmaker)
                bet365_offer = bms_offers.get("bet365")
                target_offer = bet365_offer or next(iter(bms_offers.values()))
                target_bm = target_offer.bookmaker or "bet365"

                # Sharp reference book (Pinnacle / Circa / sharp)
                sharp_offer = (
                    bms_offers.get("pinnacle")
                    or bms_offers.get("circa")
                    or next((o for k, o in bms_offers.items() if k in {"pinnacle", "circa", "sharp"}), None)
                )

                for target_outcome in target_offer.outcomes:
                    if not target_outcome.odds or target_outcome.odds.decimal <= 1.0:
                        continue

                    outcome_type_val = (
                        target_outcome.outcome_type.value
                        if isinstance(target_outcome.outcome_type, OutcomeType)
                        else str(target_outcome.outcome_type).lower()
                    )
                    is_over = outcome_type_val == "over"
                    line_val = target_outcome.point or target_offer.point
                    p_name = target_offer.player_name or target_outcome.description or target_outcome.player_name

                    # 1. Market Devigging
                    market_fair_prob: float | None = None
                    market_fair_dec: float | None = None
                    market_fair_amer: int | None = None
                    sharp_amer: int | None = None
                    sharp_dec: float | None = None

                    if sharp_offer and len(sharp_offer.outcomes) >= 2:
                        try:
                            sharp_decimals = [o.odds.decimal for o in sharp_offer.outcomes]
                            devig_res = DevigEngine.devig(sharp_decimals, method=DevigMethod.SHIN)
                            idx = next(
                                (i for i, o in enumerate(sharp_offer.outcomes) if o.name == target_outcome.name or o.outcome_type == target_outcome.outcome_type),
                                0
                            )
                            if idx < len(devig_res.fair_implied_probs):
                                market_fair_prob = devig_res.fair_implied_probs[idx]
                                market_fair_dec = devig_res.fair_decimal_odds[idx]
                                market_fair_amer = devig_res.fair_american_odds[idx]
                                sharp_dec = sharp_offer.outcomes[idx].odds.decimal
                                sharp_amer = sharp_offer.outcomes[idx].odds.american
                        except Exception as e:
                            logger.debug("Devig error: %s", e)

                    # 2. Model Projections & Distribution
                    model_fair_prob: float | None = None
                    model_fair_dec: float | None = None
                    model_fair_amer: int | None = None
                    prob_push: float = 0.0
                    stat_cat: StatCategory | None = None
                    player_proj_obj: PlayerProjection | None = None

                    if p_name and line_val is not None:
                        clean_player = PlayerNameNormalizer.clean_name(p_name).lower()
                        stat_cat = StatCategory.from_market_key(target_offer.market_key)
                        if stat_cat:
                            player_proj_obj = proj_lookup.get(clean_player, {}).get(stat_cat)

                        if player_proj_obj and player_proj_obj.projection_mean > 0:
                            mean_stat = player_proj_obj.projection_mean
                            pos_val = player_proj_obj.position
                            pos = Position(pos_val) if pos_val in Position._value2member_map_ else Position.WR
                            try:
                                is_discrete = stat_cat in {
                                    StatCategory.PASSING_TDS,
                                    StatCategory.PASSING_INTERCEPTIONS,
                                    StatCategory.RUSHING_TDS,
                                    StatCategory.RECEIVING_TDS,
                                    StatCategory.RECEPTIONS,
                                    StatCategory.ANYTIME_TD,
                                }
                                if is_discrete:
                                    dist_res = DistributionEngine.evaluate_discrete_prop(
                                        projection_mean=mean_stat,
                                        line=line_val,
                                        stat_category=stat_cat,
                                        dist_type=DistributionType.POISSON,
                                    )
                                else:
                                    dist_res = DistributionEngine.evaluate_continuous_prop(
                                        projection_mean=mean_stat,
                                        line=line_val,
                                        position=pos,
                                        stat_category=stat_cat,
                                        dist_type=DistributionType.LOG_NORMAL,
                                    )

                                prob_push = dist_res.prob_push
                                model_fair_prob = dist_res.prob_over if is_over else dist_res.prob_under
                                if model_fair_prob > 0:
                                    model_fair_dec = round(1.0 / model_fair_prob, 4)
                                    model_fair_amer = EVEngine.decimal_to_american(model_fair_dec)
                            except Exception as e:
                                logger.warning("Distribution error for %s %s: %s", p_name, stat_cat, e)


                    # Baseline fallback if needed
                    if market_fair_prob is None and model_fair_prob is None:
                        implied = target_outcome.odds.implied_probability
                        market_fair_prob = min(0.95, max(0.05, implied * 0.96))

                    # 3. Dual-Edge EV & Fractional Kelly Calculation
                    ev_res = EVEngine.calculate(
                        decimal_odds=target_outcome.odds.decimal,
                        market_fair_prob=market_fair_prob,
                        model_fair_prob=model_fair_prob,
                        prob_push=prob_push,
                        config=kelly_cfg,
                    )
                    is_quarantined = ev_res.blended_ev >= SUSPICIOUS_EV_THRESHOLD_PCT
                    quarantine_reason = (
                        f"Calculated EV is at least {SUSPICIOUS_EV_THRESHOLD_PCT:.0f}%. "
                        "Verify the exact bookmaker, participant, market, line, and price before betting."
                        if is_quarantined
                        else None
                    )

                    opp_id = cls.generate_opportunity_id(
                        event_id=event.id,
                        market_key=target_offer.market_key,
                        player_name=p_name,
                        outcome_name=target_outcome.name,
                        line=line_val,
                    )

                    tags: list[str] = []
                    if is_quarantined:
                        tags.append("Verification Required")
                    elif ev_res.blended_ev >= 7.0:
                        tags.append("High Edge 🔥")
                    elif ev_res.blended_ev >= 3.0:
                        tags.append("+EV Edge ⚡")

                    if market_fair_prob and model_fair_prob:
                        tags.append("Dual Signal 🎯")
                    elif market_fair_prob:
                        tags.append("Sharp Devig 📊")
                    elif model_fair_prob:
                        tags.append("Model Projection 🤖")

                    m_label = MARKET_DISPLAY_NAMES.get(target_offer.market_key, target_offer.market_key.replace("_", " ").title())

                    opp = MatchedEVOpportunity(
                        id=opp_id,
                        event_id=event.id,
                        game=game_str,
                        commence_time=commence_dt,
                        sport_key=event.sport_key,
                        player_name=p_name,
                        canonical_name=PlayerNameNormalizer.clean_name(p_name) if p_name else None,
                        team=player_proj_obj.team if player_proj_obj else None,
                        position=str(player_proj_obj.position) if (player_proj_obj and player_proj_obj.position) else None,
                        market_key=target_offer.market_key,
                        market_label=m_label,
                        stat_category=stat_cat,
                        line=line_val,
                        outcome_name=target_outcome.name,
                        outcome_type=target_outcome.outcome_type,
                        target_book=target_bm,
                        target_american=target_outcome.odds.american,
                        target_decimal=target_outcome.odds.decimal,
                        benchmark_book=sharp_offer.bookmaker if sharp_offer else "sharp_consensus",
                        benchmark_american=sharp_amer,
                        benchmark_decimal=sharp_dec,
                        market_fair_prob=round(market_fair_prob, 4) if market_fair_prob else None,
                        market_fair_decimal=market_fair_dec,
                        market_fair_american=market_fair_amer,
                        model_fair_prob=round(model_fair_prob, 4) if model_fair_prob else None,
                        model_fair_decimal=model_fair_dec,
                        model_fair_american=model_fair_amer,
                        blended_win_prob=ev_res.blended_win_prob,
                        prob_push=prob_push,
                        market_ev=ev_res.market_implied_ev,
                        model_ev=ev_res.model_implied_ev,
                        blended_ev=ev_res.blended_ev,
                        edge_pct=ev_res.edge_pct,
                        quarter_kelly=ev_res.quarter_kelly_fraction,
                        half_kelly=ev_res.half_kelly_fraction,
                        full_kelly=ev_res.full_kelly_fraction,
                        quarter_kelly_stake=0.0 if is_quarantined else ev_res.quarter_kelly_stake,
                        half_kelly_stake=0.0 if is_quarantined else ev_res.half_kelly_stake,
                        full_kelly_stake=0.0 if is_quarantined else ev_res.full_kelly_stake,
                        recommended_stake=0.0 if is_quarantined else ev_res.recommended_stake,
                        is_positive_ev=ev_res.is_positive_ev,
                        is_quarantined=is_quarantined,
                        quarantine_reason=quarantine_reason,
                        tags=tags,
                    )
                    matched_opportunities.append(opp)

        cache.store_opportunities(matched_opportunities)
        logger.info("Pipeline calculated %d +EV opportunities", len(matched_opportunities))
        return matched_opportunities

    @classmethod
    def get_breakdown(cls, opportunity_id: str) -> PropBreakdown | None:
        """
        Build deep prop breakdown modal payload with Chart.js curves and educational steps.
        """
        opp = cache.get_opportunity(opportunity_id)
        if not opp:
            return None

        odds_comp = [
            {
                "bookmaker": opp.target_book.title(),
                "american": opp.target_american,
                "decimal": opp.target_decimal,
                "is_target": True,
            }
        ]
        if opp.benchmark_american and opp.benchmark_decimal:
            odds_comp.append({
                "bookmaker": opp.benchmark_book.title(),
                "american": opp.benchmark_american,
                "decimal": opp.benchmark_decimal,
                "is_target": False,
            })

        chart_data = None
        stat_category = opp.stat_category or (StatCategory.from_market_key(opp.market_key) if opp.market_key else None)
        mean_val = (opp.line or 50.0) * (1.05 if opp.outcome_type == OutcomeType.OVER else 0.95)
        pos = Position(opp.position) if opp.position in Position._value2member_map_ else Position.WR

        if stat_category and opp.line is not None:
            chart_data = cls.compute_chart_curve(
                stat_category=stat_category,
                mean_proj=mean_val,
                line=opp.line,
                position=pos,
            )

        math_steps = [
            {
                "step": "1. Vig Removal (Devigging)",
                "explanation": f"Stripped bookmaker margin from sharp line to obtain fair win probability: {round((opp.market_fair_prob or opp.blended_win_prob) * 100, 2)}%",
            },
            {
                "step": "2. Expected Value Formula",
                "explanation": f"EV = [P(Win) × Decimal Odds] - [1 - P(Push)] = [{round(opp.blended_win_prob, 3)} × {opp.target_decimal}] - [{round(1.0 - opp.prob_push, 3)}] = +{opp.edge_pct}%",
            },
            {
                "step": "3. Fractional Kelly Sizing",
                "explanation": f"Optimal Growth Stake = Bankroll (${opp.quarter_kelly_stake * 4 if opp.quarter_kelly > 0 else 1000}) × Quarter Kelly Fraction ({opp.quarter_kelly}) = ${opp.recommended_stake:.2f}",
            },
        ]

        if opp.is_quarantined:
            math_steps.append({
                "step": "4. Data Verification Gate",
                "explanation": opp.quarantine_reason or "This opportunity requires source-market verification.",
            })

        return PropBreakdown(
            opportunity=opp,
            odds_comparison=odds_comp,
            devig_summary={
                "method": "Shin's Informed Trader Model",
                "target_decimal": opp.target_decimal,
                "fair_probability": opp.market_fair_prob,
                "fair_decimal": opp.market_fair_decimal,
                "fair_american": opp.market_fair_american,
            },
            distribution_summary={
                "stat_category": opp.market_label,
                "line": opp.line,
                "prob_over": opp.model_fair_prob if opp.outcome_type == OutcomeType.OVER else (1.0 - (opp.model_fair_prob or 0.5)),
                "prob_push": opp.prob_push,
            },
            chart_coordinates=chart_data,
            ev_math_steps=math_steps,
        )


pipeline_service = EVPipellineService()
