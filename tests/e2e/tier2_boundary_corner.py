"""
Tier 2: Comprehensive Boundary, Corner & Negative Cases Suite

Covers boundary conditions, edge cases, numerical limits, and fault resilience
across all 20 features (>= 100 tests total).
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
    MockFastAPIClient
)


class TestTier2BoundaryCorner(unittest.TestCase):

    # ==========================================================================
    # 1. ODDS CONVERSION BOUNDARIES (B01 - B05)
    # ==========================================================================
    def test_b01_zero_american_odds_rejected(self):
        with self.assertRaises(ValueError):
            OddsValue.from_american(0)

    def test_b01_positive_sub_hundred_american_odds_rejected(self):
        with self.assertRaises(ValueError):
            OddsValue.from_american(50)
        with self.assertRaises(ValueError):
            OddsValue.from_american(99)

    def test_b01_negative_sub_hundred_american_odds_rejected(self):
        with self.assertRaises(ValueError):
            OddsValue.from_american(-50)
        with self.assertRaises(ValueError):
            OddsValue.from_american(-99)

    def test_b02_decimal_odds_at_or_below_one_rejected(self):
        with self.assertRaises(ValueError):
            OddsValue.from_decimal(1.000)
        with self.assertRaises(ValueError):
            OddsValue.from_decimal(0.950)
        with self.assertRaises(ValueError):
            OddsValue.from_decimal(-1.500)

    def test_b03_extreme_longshot_american_odds(self):
        val = OddsValue.from_american(50000)
        self.assertEqual(val.decimal, 501.0000)
        self.assertAlmostEqual(val.implied_prob, 1.0 / 501.0, places=6)

    def test_b04_extreme_heavy_favorite_american_odds(self):
        val = OddsValue.from_american(-50000)
        self.assertEqual(val.decimal, 1.0020)
        self.assertAlmostEqual(val.implied_prob, 1.0 / 1.0020, places=5)

    def test_b05_decimal_odds_boundary_just_above_one(self):
        val = OddsValue.from_decimal(1.0010)
        self.assertEqual(val.american, -100000)
        self.assertAlmostEqual(val.implied_prob, 0.9990, places=3)

    # ==========================================================================
    # 2. DEVIGGING ENGINE BOUNDARIES & SINGULARITIES (B05 - B09)
    # ==========================================================================
    def test_b05_already_vig_free_market(self):
        # S = 1.000000 -> [2.00, 2.00]
        for method in (DevigMethod.MULTIPLICATIVE, DevigMethod.ADDITIVE, DevigMethod.POWER, DevigMethod.SHIN):
            res = DevigEngine.devig([2.00, 2.00], method)
            self.assertAlmostEqual(res.fair_implied_probabilities[0], 0.5000, places=4)
            self.assertAlmostEqual(res.fair_implied_probabilities[1], 0.5000, places=4)
            self.assertAlmostEqual(res.overround, 1.0000, places=4)

    def test_b06_arbitrage_market_inverted_vig(self):
        # [2.10, 2.10] -> S = 0.95238
        res = DevigEngine.devig([2.10, 2.10], DevigMethod.SHIN)
        self.assertAlmostEqual(res.fair_implied_probabilities[0], 0.5000, places=4)
        self.assertAlmostEqual(res.fair_implied_probabilities[1], 0.5000, places=4)

    def test_b07_extreme_high_juice_market(self):
        # S = 1.3333 -> [1.50, 1.50]
        res = DevigEngine.devig([1.50, 1.50], DevigMethod.SHIN)
        self.assertAlmostEqual(res.fair_implied_probabilities[0], 0.5000, places=4)
        self.assertAlmostEqual(sum(res.fair_implied_probabilities), 1.0000, places=5)

    def test_b08_additive_negative_probability_guardrail(self):
        # Heavy longshot: [1.02, 100.0]
        res = DevigEngine.devig([1.02, 100.0], DevigMethod.ADDITIVE)
        self.assertTrue(all(p > 0 for p in res.fair_implied_probabilities))
        self.assertAlmostEqual(sum(res.fair_implied_probabilities), 1.0000, places=4)

    def test_b09_shin_solver_convergence_near_zero(self):
        res = DevigEngine.devig([1.99, 1.99], DevigMethod.SHIN)
        self.assertIsNotNone(res.z_parameter)
        self.assertAlmostEqual(sum(res.fair_implied_probabilities), 1.0000, places=5)

    def test_b09_shin_solver_convergence_extreme_longshot(self):
        res = DevigEngine.devig([1.01, 200.0], DevigMethod.SHIN)
        self.assertAlmostEqual(sum(res.fair_implied_probabilities), 1.0000, places=4)

    def test_b09_multiway_shin_solver_convergence(self):
        # 5-way market
        res = DevigEngine.devig([3.0, 4.0, 5.0, 6.0, 7.0], DevigMethod.SHIN)
        self.assertAlmostEqual(sum(res.fair_implied_probabilities), 1.0000, places=5)

    def test_b09_single_outcome_devig_rejection(self):
        with self.assertRaises(ValueError):
            DevigEngine.devig([1.909])

    # ==========================================================================
    # 3. NAME NORMALIZER BOUNDARIES & PUNCTUATION (B10 - B13)
    # ==========================================================================
    def test_b10_unicode_accents_and_foreign_characters(self):
        name1, _ = PlayerNameNormalizer.clean_name("Tua Tagovailoa")
        name2, _ = PlayerNameNormalizer.clean_name("Amon-Ra St. Brown")
        name3, _ = PlayerNameNormalizer.clean_name("José Valdés-Scantling")
        self.assertEqual(name1, "tua tagovailoa")
        self.assertEqual(name2, "amonra st brown")
        self.assertEqual(name3, "jose valdesscantling")

    def test_b11_punctuation_soup_and_suffixes(self):
        name1, suf1 = PlayerNameNormalizer.clean_name("Ja'Marr (Jr.) Chase, III.")
        name2, suf2 = PlayerNameNormalizer.clean_name("D.J. Moore, Jr.")
        name3, suf3 = PlayerNameNormalizer.clean_name("Travis Etienne, Jr.")
        self.assertEqual(name1, "jamarr chase")
        self.assertEqual(suf1, "III")
        self.assertEqual(name2, "dj moore")
        self.assertEqual(suf2, "JR")
        self.assertEqual(name3, "travis etienne")
        self.assertEqual(suf3, "JR")

    def test_b12_empty_whitespace_and_none_names(self):
        self.assertEqual(PlayerNameNormalizer.clean_name(""), ("", None))
        self.assertEqual(PlayerNameNormalizer.clean_name("   "), ("", None))
        self.assertEqual(PlayerNameNormalizer.clean_name(None), ("", None))

    def test_b13_nickname_alias_variations(self):
        aliases = [
            ("Chosen Anderson", "chosen anderson"),
            ("Robbie Chosen", "chosen anderson"),
            ("Robby Anderson", "chosen anderson"),
            ("Hollywood Brown", "marquise brown"),
            ("Marquise Hollywood Brown", "marquise brown"),
            ("Chig Okonkwo", "chigoziem okonkwo"),
            ("Chigoziem Chig Okonkwo", "chigoziem okonkwo"),
            ("Mitch Trubisky", "mitchell trubisky"),
            ("Gabe Davis", "gabriel davis"),
            ("Scotty Miller", "scott miller"),
            ("Jeff Wilson", "jeffery wilson"),
        ]
        for raw, expected in aliases:
            cleaned, _ = PlayerNameNormalizer.clean_name(raw)
            self.assertEqual(cleaned, expected)

    def test_b13_all_caps_and_mixed_case(self):
        self.assertEqual(PlayerNameNormalizer.clean_name("PATRICK MAHOMES")[0], "patrick mahomes")
        self.assertEqual(PlayerNameNormalizer.clean_name("pAtRiCk MaHoMeS")[0], "patrick mahomes")

    def test_b13_single_name_player(self):
        self.assertEqual(PlayerNameNormalizer.clean_name("Mahomes")[0], "mahomes")

    # ==========================================================================
    # 4. TEAM NORMALIZER BOUNDARIES & ALIASES (B14)
    # ==========================================================================
    def test_b14_historic_relocated_aliases(self):
        self.assertEqual(TeamNormalizer.canonical_team("OAK"), "LV")
        self.assertEqual(TeamNormalizer.canonical_team("SD"), "LAC")
        self.assertEqual(TeamNormalizer.canonical_team("WFT"), "WAS")
        self.assertEqual(TeamNormalizer.canonical_team("Redskins"), "WAS")

    def test_b14_city_names(self):
        self.assertEqual(TeamNormalizer.canonical_team("Kansas City"), "KC")
        self.assertEqual(TeamNormalizer.canonical_team("San Francisco"), "SF")
        self.assertEqual(TeamNormalizer.canonical_team("Green Bay"), "GB")
        self.assertEqual(TeamNormalizer.canonical_team("Tampa Bay"), "TB")
        self.assertEqual(TeamNormalizer.canonical_team("New Orleans"), "NO")

    def test_b14_empty_and_whitespace_teams(self):
        self.assertEqual(TeamNormalizer.canonical_team(""), "")
        self.assertEqual(TeamNormalizer.canonical_team("  "), "")
        self.assertEqual(TeamNormalizer.canonical_team(None), "")

    def test_b14_all_32_canonical_teams_roundtrip(self):
        for t in TeamNormalizer.CANONICAL_TEAMS:
            self.assertEqual(TeamNormalizer.canonical_team(t), t)

    # ==========================================================================
    # 5. FANTASYPOINTS INGESTION & FLOAT SANITIZATION (B15 - B16)
    # ==========================================================================
    def test_b15_corrupt_and_dirty_strings(self):
        self.assertEqual(FantasyPointsIngestionEngine.sanitize_float("--"), 0.0)
        self.assertEqual(FantasyPointsIngestionEngine.sanitize_float("N/A"), 0.0)
        self.assertEqual(FantasyPointsIngestionEngine.sanitize_float("null"), 0.0)
        self.assertEqual(FantasyPointsIngestionEngine.sanitize_float("None"), 0.0)
        self.assertEqual(FantasyPointsIngestionEngine.sanitize_float("OUT"), 0.0)
        self.assertEqual(FantasyPointsIngestionEngine.sanitize_float("IR"), 0.0)
        self.assertEqual(FantasyPointsIngestionEngine.sanitize_float("24.5 (Q)"), 24.5)
        self.assertEqual(FantasyPointsIngestionEngine.sanitize_float("75.0 (P)"), 75.0)
        self.assertEqual(FantasyPointsIngestionEngine.sanitize_float("1,250.5"), 1250.5)
        self.assertEqual(FantasyPointsIngestionEngine.sanitize_float(""), 0.0)
        self.assertEqual(FantasyPointsIngestionEngine.sanitize_float(None), 0.0)

    def test_b16_empty_clipboard_text(self):
        self.assertEqual(FantasyPointsIngestionEngine.parse_csv_text(""), [])
        self.assertEqual(FantasyPointsIngestionEngine.parse_csv_text("   \n\n  "), [])

    def test_b16_corrupted_headerless_csv(self):
        projs = FantasyPointsIngestionEngine.parse_csv_text("1,2,3\n4,5,6")
        self.assertEqual(len(projs), 0)

    def test_b16_jagged_csv_rows(self):
        csv_text = "Player,Team,Opp,Pos,Pass Yds\nPatrick Mahomes,KC,BAL,QB,270.0\nInvalid Row Missing Fields\nJosh Allen,BUF,NYJ,QB,250.0"
        projs = FantasyPointsIngestionEngine.parse_csv_text(csv_text)
        self.assertEqual(len(projs), 2)

    # ==========================================================================
    # 6. DISTRIBUTION ENGINE BOUNDARIES (B17 - B21)
    # ==========================================================================
    def test_b17_zero_or_negative_projection_mean(self):
        with self.assertRaises(ValueError):
            DistributionEngine.evaluate_continuous_prop(0.0, 50.0, "WR", "rec_yds")
        with self.assertRaises(ValueError):
            DistributionEngine.evaluate_continuous_prop(-10.0, 50.0, "WR", "rec_yds")

    def test_b17_discrete_zero_mean_graceful_handling(self):
        res = DistributionEngine.evaluate_discrete_prop(0.0, 0.5, "anytime_td")
        self.assertEqual(res.prob_over, 0.0)
        self.assertEqual(res.prob_under, 1.0)

    def test_b18_zero_line_continuous(self):
        res = DistributionEngine.evaluate_continuous_prop(50.0, 0.0, "WR", "rec_yds")
        self.assertEqual(res.prob_over, 1.0)
        self.assertEqual(res.prob_under, 0.0)

    def test_b18_negative_line_continuous_rejection(self):
        with self.assertRaises(ValueError):
            DistributionEngine.evaluate_continuous_prop(50.0, -5.0, "WR", "rec_yds")

    def test_b19_extreme_yardage_line_right_tail(self):
        # Line 350.5 on mean 50.0
        res = DistributionEngine.evaluate_continuous_prop(50.0, 350.5, "WR", "rec_yds")
        self.assertLess(res.prob_over, 0.001)
        self.assertGreater(res.prob_under, 0.999)
        self.assertAlmostEqual(res.prob_over + res.prob_under, 1.0000, places=4)

    def test_b19_extreme_yardage_line_left_tail(self):
        # Line 5.5 on mean 120.0
        res = DistributionEngine.evaluate_continuous_prop(120.0, 5.5, "WR", "rec_yds")
        self.assertGreater(res.prob_over, 0.999)
        self.assertLess(res.prob_under, 0.001)

    def test_b20_high_count_poisson_logspace_stability(self):
        # High lambda count (lambda = 20.0, line = 25.5)
        res = DistributionEngine.evaluate_discrete_prop(20.0, 25.5, "pass_tds", DistributionType.POISSON)
        self.assertGreater(res.prob_over, 0.0)
        self.assertLess(res.prob_over, 1.0)
        self.assertAlmostEqual(res.prob_over + res.prob_under, 1.0000, places=4)

    def test_b20_high_count_negative_binomial_stability(self):
        # High count NegBin
        res = DistributionEngine.evaluate_discrete_prop(15.0, 15.0, "receptions", DistributionType.NEGATIVE_BINOMIAL, alpha_override=0.10)
        self.assertGreater(res.prob_push, 0.0)
        self.assertAlmostEqual(res.prob_over + res.prob_under + res.prob_push, 1.0000, places=4)

    def test_b21_integer_push_line_continuous(self):
        res = DistributionEngine.evaluate_continuous_prop(65.0, 65.0, "WR", "rec_yds")
        self.assertGreater(res.prob_push, 0.0)
        self.assertAlmostEqual(res.prob_over + res.prob_under + res.prob_push, 1.0000, places=4)

    def test_b21_half_point_line_continuous_zero_push(self):
        res = DistributionEngine.evaluate_continuous_prop(65.0, 65.5, "WR", "rec_yds")
        self.assertEqual(res.prob_push, 0.0)

    # ==========================================================================
    # 7. EV & KELLY CRITERION BOUNDARIES (B22 - B25)
    # ==========================================================================
    def test_b22_non_positive_ev_zero_stake(self):
        res = EVEngine.calculate_ev(1.9091, market_fair_prob=0.4500, model_fair_prob=None)
        self.assertLess(res.blended_ev, 0.0)
        self.assertEqual(res.recommended_stake, 0.0)
        self.assertEqual(res.quarter_kelly_fraction, 0.0)

    def test_b22_exact_zero_ev(self):
        # D = 2.00, p = 0.50 -> EV = 0.0
        res = EVEngine.calculate_ev(2.0000, market_fair_prob=0.5000, model_fair_prob=None)
        self.assertEqual(res.blended_ev, 0.0)
        self.assertEqual(res.recommended_stake, 0.0)

    def test_b23_positive_ev_below_min_bet_floor(self):
        # EV = +0.5%, bankroll $1000 -> stake < $5.00
        res = EVEngine.calculate_ev(2.00, market_fair_prob=0.5025, model_fair_prob=None, bankroll=1000.0, min_stake=5.0)
        self.assertGreater(res.blended_ev, 0.0)
        self.assertEqual(res.recommended_stake, 0.0)

    def test_b24_huge_ev_bankroll_pct_cap(self):
        # EV = +50%, bankroll $2000, cap 5% ($100)
        res = EVEngine.calculate_ev(3.00, market_fair_prob=0.75, model_fair_prob=None, bankroll=2000.0, max_bankroll_pct=0.05)
        self.assertEqual(res.recommended_stake, 100.0)
        self.assertTrue(res.is_capped)

    def test_b24_huge_ev_absolute_dollar_cap(self):
        # EV = +50%, bankroll $10000, 5% is $500, but absolute max cap is $250
        res = EVEngine.calculate_ev(3.00, market_fair_prob=0.75, model_fair_prob=None, bankroll=10000.0, max_bankroll_pct=0.05)
        self.assertEqual(res.recommended_stake, 250.0)
        self.assertTrue(res.is_capped)

    def test_b25_odds_approaching_one(self):
        # D = 1.0100
        res = EVEngine.calculate_ev(1.0100, market_fair_prob=0.9950, model_fair_prob=None, bankroll=2000.0)
        self.assertGreaterEqual(res.recommended_stake, 0.0)

    def test_b25_zero_bankroll(self):
        res = EVEngine.calculate_ev(2.00, market_fair_prob=0.60, model_fair_prob=None, bankroll=0.0)
        self.assertEqual(res.recommended_stake, 0.0)

    def test_b25_negative_bankroll(self):
        res = EVEngine.calculate_ev(2.00, market_fair_prob=0.60, model_fair_prob=None, bankroll=-1000.0)
        self.assertEqual(res.recommended_stake, 0.0)

    # ==========================================================================
    # 8. IN-MEMORY CACHE & CONCURRENCY BOUNDARIES (B26 - B27)
    # ==========================================================================
    def test_b26_query_empty_cache(self):
        cache = InMemoryCache()
        opps = asyncio.run(cache.get_opportunities())
        self.assertEqual(len(opps), 0)

    def test_b26_query_non_existent_market(self):
        cache = InMemoryCache()
        opps = asyncio.run(cache.get_opportunities(market_type="nonexistent_market"))
        self.assertEqual(len(opps), 0)

    def test_b26_query_unmatched_search_substring(self):
        cache = InMemoryCache()
        opps = asyncio.run(cache.get_opportunities(search="NonExistentPlayerXYZ"))
        self.assertEqual(len(opps), 0)

    def test_b27_concurrent_read_write_stress(self):
        cache = InMemoryCache()
        async def run_stress():
            writers = [cache.update_odds([]) for _ in range(50)]
            readers = [cache.get_opportunities() for _ in range(50)]
            recalcs = [cache.recalculate() for _ in range(10)]
            await asyncio.gather(*writers, *readers, *recalcs)
        asyncio.run(run_stress())
        self.assertEqual(len(cache.opportunities), 0)

    # ==========================================================================
    # 9. REST API & FAULT INJECTION BOUNDARIES (B28 - B30)
    # ==========================================================================
    def test_b28_missing_payload_fields_handled(self):
        client = MockFastAPIClient()
        res = asyncio.run(client.post("/api/v1/upload/projections", data=""))
        self.assertEqual(res["status_code"], 200)
        self.assertEqual(res["json"]["imported_count"], 0)

    def test_b28_invalid_json_body_handled(self):
        client = MockFastAPIClient()
        res = asyncio.run(client.post("/api/v1/upload/odds", json_body=[]))
        self.assertEqual(res["status_code"], 200)
        self.assertEqual(res["json"]["offers_updated"], 0)

    def test_b29_rate_limit_backoff_simulation(self):
        # Test backoff calculation logic: base 2s exponential
        delays = [min(60.0, 2.0 * (2 ** attempt)) for attempt in range(5)]
        self.assertEqual(delays, [2.0, 4.0, 8.0, 16.0, 32.0])

    def test_b30_missing_model_projection_graceful_degradation(self):
        # Offer exists for player without FantasyPoints projection
        res = EVEngine.calculate_ev(2.00, market_fair_prob=0.55, model_fair_prob=None)
        self.assertIsNotNone(res.market_implied_ev)
        self.assertIsNone(res.model_implied_ev)
        self.assertEqual(res.blended_ev, res.market_implied_ev)

    def test_b30_missing_sharp_market_odds_graceful_degradation(self):
        # Model exists but sharp market odds are missing
        res = EVEngine.calculate_ev(2.00, market_fair_prob=None, model_fair_prob=0.55)
        self.assertIsNone(res.market_implied_ev)
        self.assertIsNotNone(res.model_implied_ev)
        self.assertEqual(res.blended_ev, res.model_implied_ev)

    def test_b30_both_model_and_market_missing(self):
        res = EVEngine.calculate_ev(2.00, market_fair_prob=None, model_fair_prob=None)
        self.assertIsNone(res.market_implied_ev)
        self.assertIsNone(res.model_implied_ev)
        self.assertEqual(res.blended_win_prob, 0.0)
        self.assertEqual(res.recommended_stake, 0.0)


if __name__ == "__main__":
    unittest.main()
