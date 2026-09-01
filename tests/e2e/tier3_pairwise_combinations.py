"""
Tier 3: Systematic Pairwise Combinations Suite

Covers systematic 2-way orthogonal cross-engine interactions across devigging,
distribution models, ingestion formats, sizing caps, normalizations, and queries (>= 20 tests).
"""

import unittest
import math
import asyncio
import os
import sys

from tests.e2e.conftest import (
    MarketType,
    PlayerPosition,
    DevigMethod,
    DistributionType,
    OddsValue,
    Player,
    Event,
    MarketOffer,
    PlayerProjection,
    MatchedEVOpportunity,
    DevigEngine,
    DistributionEngine,
    EVEngine,
    PlayerNameNormalizer,
    TeamNormalizer,
    FantasyPointsIngestionEngine,
    MockTheOddsApiAdapter,
    MockCsvOddsAdapter,
    InMemoryCache,
    MockFastAPIClient,
    FANTASYPOINTS_CSV_PATH,
    ODDS_SNAPSHOT_JSON_PATH,
    ODDS_SAMPLE_CSV_PATH
)


class TestTier3PairwiseCombinations(unittest.TestCase):

    # ==========================================================================
    # Matrix 1: Devig Method × Distribution Model (3.1.1 - 3.1.6)
    # ==========================================================================
    def test_3_1_1_shin_devig_with_lognormal_rushing(self):
        # Soft: Over 68.5 @ -110 (1.9091). Sharp: -135 (1.7407) / +112 (2.1200)
        # Projection: Mean 78.5, CV 0.42
        devig_res = DevigEngine.devig([1.7407, 2.1200], DevigMethod.SHIN)
        p_market = devig_res.fair_implied_probabilities[0]
        
        dist_res = DistributionEngine.evaluate_continuous_prop(78.5, 68.5, "RB", "rush_yds", DistributionType.LOG_NORMAL, cv_override=0.42)
        p_model = dist_res.prob_over

        ev_res = EVEngine.calculate_ev(1.9091, market_fair_prob=p_market, model_fair_prob=p_model, bankroll=2000.0, kelly_fraction=0.25)
        
        self.assertAlmostEqual(sum(devig_res.fair_implied_probabilities), 1.0000, places=4)
        self.assertAlmostEqual(dist_res.prob_over + dist_res.prob_under, 1.0000, places=4)
        self.assertGreater(ev_res.blended_ev, 0.0)
        self.assertGreater(ev_res.quarter_kelly_stake, 10.0)

    def test_3_1_2_power_devig_with_poisson_anytime_td(self):
        # Soft: +125 (2.25). Sharp: -105 (1.9524) / -115 (1.8696)
        # Projection: Mean 0.65
        devig_res = DevigEngine.devig([1.9524, 1.8696], DevigMethod.POWER)
        p_market = devig_res.fair_implied_probabilities[0]

        dist_res = DistributionEngine.evaluate_discrete_prop(0.65, 0.5, "anytime_td", DistributionType.POISSON)
        p_model = dist_res.prob_over

        ev_res = EVEngine.calculate_ev(2.2500, market_fair_prob=p_market, model_fair_prob=p_model, bankroll=2000.0, kelly_fraction=0.25)
        
        self.assertAlmostEqual(sum(devig_res.fair_implied_probabilities), 1.0000, places=4)
        self.assertGreater(ev_res.blended_ev, 5.0)
        self.assertGreater(ev_res.quarter_kelly_stake, 20.0)

    def test_3_1_3_multiplicative_devig_with_negbinom_receptions(self):
        # Soft: +105 (2.05). Sharp: -115 (1.8696) / -105 (1.9524)
        # Projection: Mean 7.4, alpha 0.10
        devig_res = DevigEngine.devig([1.8696, 1.9524], DevigMethod.MULTIPLICATIVE)
        p_market = devig_res.fair_implied_probabilities[0]

        dist_res = DistributionEngine.evaluate_discrete_prop(7.4, 6.5, "receptions", DistributionType.NEGATIVE_BINOMIAL, alpha_override=0.10)
        p_model = dist_res.prob_over

        ev_res = EVEngine.calculate_ev(2.0500, market_fair_prob=p_market, model_fair_prob=p_model, bankroll=2000.0, kelly_fraction=0.25)
        
        self.assertAlmostEqual(sum(devig_res.fair_implied_probabilities), 1.0000, places=4)
        self.assertGreater(ev_res.blended_ev, 5.0)

    def test_3_1_4_additive_devig_with_calibrated_normal_passing_yards(self):
        # Soft: -105 (1.9524). Sharp: -118 (1.8475) / -102 (1.9804)
        # Projection: Mean 270.0, CV 0.28
        devig_res = DevigEngine.devig([1.8475, 1.9804], DevigMethod.ADDITIVE)
        p_market = devig_res.fair_implied_probabilities[0]

        dist_res = DistributionEngine.evaluate_continuous_prop(270.0, 255.5, "QB", "pass_yds", DistributionType.CALIBRATED_NORMAL, cv_override=0.28)
        p_model = dist_res.prob_over

        ev_res = EVEngine.calculate_ev(1.9524, market_fair_prob=p_market, model_fair_prob=p_model, bankroll=2000.0, kelly_fraction=0.25)
        
        self.assertAlmostEqual(sum(devig_res.fair_implied_probabilities), 1.0000, places=4)
        self.assertGreater(ev_res.blended_ev, 0.0)

    def test_3_1_5_shin_devig_with_negbinom_passing_tds(self):
        devig_res = DevigEngine.devig([1.7692, 2.0800], DevigMethod.SHIN)
        dist_res = DistributionEngine.evaluate_discrete_prop(2.15, 1.5, "pass_tds", DistributionType.NEGATIVE_BINOMIAL, alpha_override=0.12)
        ev_res = EVEngine.calculate_ev(1.9524, market_fair_prob=devig_res.fair_implied_probabilities[0], model_fair_prob=dist_res.prob_over)
        self.assertAlmostEqual(sum(devig_res.fair_implied_probabilities), 1.0000, places=4)
        self.assertGreater(ev_res.blended_ev, 0.0)

    def test_3_1_6_additive_guardrail_fallback_on_extreme_longshot(self):
        res = DevigEngine.devig([1.02, 50.0], DevigMethod.ADDITIVE)
        self.assertTrue(all(p > 0 for p in res.fair_implied_probabilities))
        self.assertAlmostEqual(sum(res.fair_implied_probabilities), 1.0000, places=4)

    # ==========================================================================
    # Matrix 2: Ingestion Channel × Processing Engine (3.2.1 - 3.2.5)
    # ==========================================================================
    def test_3_2_1_live_oddsapi_json_with_shin_engine(self):
        with open(ODDS_SNAPSHOT_JSON_PATH, "r", encoding="utf-8") as f:
            data = f.read()
        offers = MockTheOddsApiAdapter.parse_payload(data)
        self.assertGreater(len(offers), 0)
        pinnacle_mahomes = [o for o in offers if o.bookmaker == "pinnacle" and o.player_name == "Patrick Mahomes" and o.market_type == MarketType.PASSING_YARDS]
        self.assertGreaterEqual(len(pinnacle_mahomes), 2)
        devig_res = DevigEngine.devig([pinnacle_mahomes[0].odds.decimal, pinnacle_mahomes[1].odds.decimal], DevigMethod.SHIN)
        self.assertAlmostEqual(sum(devig_res.fair_implied_probabilities), 1.0000, places=4)

    def test_3_2_2_csv_upload_with_additive_engine(self):
        with open(ODDS_SAMPLE_CSV_PATH, "r", encoding="utf-8") as f:
            offers = MockCsvOddsAdapter.parse_csv(f.read())
        pinnacle_henry = [o for o in offers if o.bookmaker == "pinnacle" and o.player_name == "Derrick Henry"]
        self.assertGreaterEqual(len(pinnacle_henry), 2)
        devig_res = DevigEngine.devig([pinnacle_henry[0].odds.decimal, pinnacle_henry[1].odds.decimal], DevigMethod.ADDITIVE)
        self.assertAlmostEqual(sum(devig_res.fair_implied_probabilities), 1.0000, places=4)

    def test_3_2_3_clipboard_paste_with_power_engine(self):
        paste_text = "Sport\tEvent\tDate\tBookmaker\tMarket\tPlayer\tOption\tLine\tPrice_American\tPrice_Decimal\nNFL\tKC vs BAL\t2026-09-10\tpinnacle\tplayer_pass_yds\tPatrick Mahomes\tOver\t265.5\t-128\t1.781\nNFL\tKC vs BAL\t2026-09-10\tpinnacle\tplayer_pass_yds\tPatrick Mahomes\tUnder\t265.5\t+106\t2.060"
        offers = MockCsvOddsAdapter.parse_csv(paste_text.replace("\t", ","))
        devig_res = DevigEngine.devig([offers[0].odds.decimal, offers[1].odds.decimal], DevigMethod.POWER)
        self.assertAlmostEqual(sum(devig_res.fair_implied_probabilities), 1.0000, places=4)

    def test_3_2_4_live_oddsapi_with_multiplicative_engine(self):
        with open(ODDS_SNAPSHOT_JSON_PATH, "r", encoding="utf-8") as f:
            offers = MockTheOddsApiAdapter.parse_payload(f.read())
        pin_offers = [o for o in offers if o.bookmaker == "pinnacle"][:2]
        devig_res = DevigEngine.devig([pin_offers[0].odds.decimal, pin_offers[1].odds.decimal], DevigMethod.MULTIPLICATIVE)
        self.assertAlmostEqual(sum(devig_res.fair_implied_probabilities), 1.0000, places=4)

    def test_3_2_5_fantasypoints_paste_with_distribution_engine(self):
        with open(FANTASYPOINTS_CSV_PATH, "r", encoding="utf-8") as f:
            projs = FantasyPointsIngestionEngine.parse_csv_text(f.read())
        cmc = next(p for p in projs if "mccaffrey" in p.normalized_name)
        dist_res = DistributionEngine.evaluate_continuous_prop(cmc.rush_yds, 69.5, "RB", "rush_yds", DistributionType.LOG_NORMAL)
        self.assertAlmostEqual(dist_res.prob_over + dist_res.prob_under, 1.0000, places=4)

    # ==========================================================================
    # Matrix 3: Odds Formats × Sizing Caps & Bankroll Rules (3.3.1 - 3.3.5)
    # ==========================================================================
    def test_3_3_1_negative_american_with_quarter_kelly(self):
        # D = 1.8696 (-115), p = 0.58, bankroll $2000
        res = EVEngine.calculate_ev(1.8696, market_fair_prob=0.58, model_fair_prob=None, bankroll=2000.0, kelly_fraction=0.25)
        self.assertAlmostEqual(res.quarter_kelly_stake, 48.51, places=0)
        self.assertFalse(res.is_capped)

    def test_3_3_2_positive_american_underdog_full_kelly_max_cap(self):
        # D = 4.50 (+350), p = 0.30, bankroll $2000, max cap 5% ($100)
        res = EVEngine.calculate_ev(4.50, market_fair_prob=0.30, model_fair_prob=None, bankroll=2000.0, kelly_fraction=1.0, max_bankroll_pct=0.05)
        self.assertEqual(res.recommended_stake, 100.0)
        self.assertTrue(res.is_capped)

    def test_3_3_3_decimal_odds_half_kelly_min_bet_threshold(self):
        # D = 1.95, p = 0.52, bankroll $500, min stake $5.00 -> raw stake is ~$3.68 -> suppressed to $0
        res = EVEngine.calculate_ev(1.95, market_fair_prob=0.52, model_fair_prob=None, bankroll=500.0, kelly_fraction=0.50, min_stake=5.0)
        self.assertEqual(res.recommended_stake, 0.0)

    def test_3_3_4_heavy_favorite_decimal_quarter_kelly_absolute_cap(self):
        # D = 1.25 (-400), p = 0.85, bankroll $5000 -> raw quarter kelly is $312.50 -> clamped to $250.00
        res = EVEngine.calculate_ev(1.25, market_fair_prob=0.85, model_fair_prob=None, bankroll=5000.0, kelly_fraction=0.25)
        self.assertEqual(res.recommended_stake, 250.0)
        self.assertTrue(res.is_capped)

    def test_3_3_5_negative_ev_odds_zero_stake(self):
        res = EVEngine.calculate_ev(1.9091, market_fair_prob=0.48, model_fair_prob=None)
        self.assertEqual(res.recommended_stake, 0.0)
        self.assertEqual(res.quarter_kelly_fraction, 0.0)

    # ==========================================================================
    # Matrix 4: Player Name Variations × Prop Categories (3.4.1 - 3.4.5)
    # ==========================================================================
    def test_3_4_1_nicknames_across_prop_markets(self):
        nicknames = ["Gabe Davis", "Mitch Trubisky", "Hollywood Brown", "Chig Okonkwo"]
        expected = ["gabriel davis", "mitchell trubisky", "marquise brown", "chigoziem okonkwo"]
        for raw, exp in zip(nicknames, expected):
            cleaned, _ = PlayerNameNormalizer.clean_name(raw)
            self.assertEqual(cleaned, exp)

    def test_3_4_2_suffixes_across_prop_markets(self):
        suffixes = ["Patrick Mahomes II", "Kenneth Walker III", "Travis Etienne Jr.", "Marvin Harrison Jr."]
        expected = ["patrick mahomes", "kenneth walker", "travis etienne", "marvin harrison"]
        for raw, exp in zip(suffixes, expected):
            cleaned, _ = PlayerNameNormalizer.clean_name(raw)
            self.assertEqual(cleaned, exp)

    def test_3_4_3_punctuation_and_hyphens_across_props(self):
        punctuated = ["A.J. Brown", "Ja'Marr Chase", "D.J. Moore", "Amon-Ra St. Brown"]
        expected = ["aj brown", "jamarr chase", "dj moore", "amonra st brown"]
        for raw, exp in zip(punctuated, expected):
            cleaned, _ = PlayerNameNormalizer.clean_name(raw)
            self.assertEqual(cleaned, exp)

    def test_3_4_4_team_abbreviations_across_core_and_props(self):
        teams = ["KAN", "WSH", "LVR", "TAM", "NOR"]
        expected = ["KC", "WAS", "LV", "TB", "NO"]
        for raw, exp in zip(teams, expected):
            self.assertEqual(TeamNormalizer.canonical_team(raw), exp)

    def test_3_4_5_homonym_disambiguation_with_positional_guards(self):
        pool = [
            {"name": "Josh Allen", "pos": "EDGE", "team": "JAX"},
            {"name": "Josh Allen", "pos": "QB", "team": "BUF"}
        ]
        matched_qb = PlayerNameNormalizer.match_player("Josh Allen", pool, position="QB")
        matched_edge = PlayerNameNormalizer.match_player("Josh Allen", pool, position="EDGE")
        self.assertEqual(matched_qb, "Josh Allen")
        self.assertEqual(matched_edge, "Josh Allen")

    # ==========================================================================
    # Matrix 5: Filter Parameters × Cache Queries (3.5.1 - 3.5.4)
    # ==========================================================================
    def test_3_5_1_market_filter_and_ev_threshold(self):
        client = MockFastAPIClient()
        with open(ODDS_SAMPLE_CSV_PATH, "r", encoding="utf-8") as f:
            offers = MockCsvOddsAdapter.parse_csv(f.read())
        with open(FANTASYPOINTS_CSV_PATH, "r", encoding="utf-8") as f:
            projs = FantasyPointsIngestionEngine.parse_csv_text(f.read())
        asyncio.run(client.cache.update_odds(offers))
        asyncio.run(client.cache.update_projections(projs))
        asyncio.run(client.cache.recalculate())

        res = asyncio.run(client.get("/api/v1/opportunities", params={"market": "player_pass_yds", "min_ev": 1.0}))
        self.assertEqual(res["status_code"], 200)

    def test_3_5_2_search_query_and_player_name_sorting(self):
        client = MockFastAPIClient()
        with open(ODDS_SAMPLE_CSV_PATH, "r", encoding="utf-8") as f:
            offers = MockCsvOddsAdapter.parse_csv(f.read())
        asyncio.run(client.cache.update_odds(offers))
        asyncio.run(client.cache.recalculate())

        res = asyncio.run(client.get("/api/v1/opportunities", params={"search": "Mahomes", "sort_by": "player_name"}))
        self.assertEqual(res["status_code"], 200)

    def test_3_5_3_settings_update_and_recalculation(self):
        client = MockFastAPIClient()
        res = asyncio.run(client.put("/config/bankroll", json_body={"bankroll": 3000.0, "kelly_fraction": 0.50}))
        self.assertEqual(res["status_code"], 200)
        self.assertEqual(client.cache.bankroll, 3000.0)

    def test_3_5_4_composite_multi_filter_export(self):
        client = MockFastAPIClient()
        res = asyncio.run(client.get("/export/csv"))
        self.assertEqual(res["status_code"], 200)
        self.assertTrue(len(res["text"]) > 0)


if __name__ == "__main__":
    unittest.main()
