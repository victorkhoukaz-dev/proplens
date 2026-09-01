"""
Tier 4: Comprehensive Real-World Application Workloads Suite

Covers full 16-game NFL weekly slates, multi-book live polling, FantasyPoints upload
recalculation, full end-to-end user journeys, and fault resilience (>= 10 tests).
"""

import unittest
import math
import asyncio
import time
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


class TestTier4RealWorldWorkloads(unittest.TestCase):

    # ==========================================================================
    # Workload 1: Full NFL Game-Week Slate Simulation
    # ==========================================================================
    def test_w01_full_game_week_slate_ingestion(self):
        cache = InMemoryCache()
        
        # Load sample odds & projections
        with open(ODDS_SNAPSHOT_JSON_PATH, "r", encoding="utf-8") as f:
            offers = MockTheOddsApiAdapter.parse_payload(f.read())
        with open(FANTASYPOINTS_CSV_PATH, "r", encoding="utf-8") as f:
            projections = FantasyPointsIngestionEngine.parse_csv_text(f.read())

        # Synthesize 16-game slate offers (replicate across teams to simulate 700+ props)
        full_offers = []
        for i in range(15):
            for o in offers:
                full_offers.append(
                    MarketOffer(
                        offer_id=f"{o.offer_id}_batch_{i}",
                        event_id=f"{o.event_id}_{i}",
                        bookmaker=o.bookmaker,
                        market_type=o.market_type,
                        player_name=o.player_name,
                        side=o.side,
                        point=o.point,
                        odds=o.odds,
                        timestamp=o.timestamp
                    )
                )

        start_time = time.perf_counter()
        asyncio.run(cache.update_odds(full_offers))
        asyncio.run(cache.update_projections(projections))
        asyncio.run(cache.recalculate())
        elapsed_ms = (time.perf_counter() - start_time) * 1000.0

        # Assert sub-250ms processing
        self.assertLess(elapsed_ms, 250.0)
        self.assertGreater(len(cache.opportunities), 0)
        self.assertEqual(len(cache.odds), len(full_offers))

    # ==========================================================================
    # Workload 2: End-to-End User Journey Simulation
    # ==========================================================================
    def test_w02_end_to_end_user_journey_testclient(self):
        client = MockFastAPIClient()

        async def run_journey():
            # Step 1: Health check
            res_health = await client.get("/health")
            self.assertEqual(res_health["status_code"], 200)

            # Step 2: Upload Projections CSV
            with open(FANTASYPOINTS_CSV_PATH, "r", encoding="utf-8") as f:
                csv_proj = f.read()
            res_proj = await client.post("/api/v1/upload/projections", data=csv_proj)
            self.assertEqual(res_proj["status_code"], 200)
            self.assertGreater(res_proj["json"]["imported_count"], 0)

            # Step 3: Upload Odds CSV
            with open(ODDS_SAMPLE_CSV_PATH, "r", encoding="utf-8") as f:
                csv_odds = f.read()
            res_odds = await client.post("/api/v1/upload/odds", data=csv_odds)
            self.assertEqual(res_odds["status_code"], 200)
            self.assertGreater(res_odds["json"]["offers_updated"], 0)

            # Step 4: Query opportunities with filter
            res_opps = await client.get("/api/v1/opportunities", params={"min_ev": 1.0, "sort_by": "blended_ev"})
            self.assertEqual(res_opps["status_code"], 200)
            self.assertIn("items", res_opps["json"])

            # Step 5: Fetch Prop Breakdown Modal for top opportunity
            res_modal = await client.get("/api/v1/opportunities/opp_1/breakdown")
            self.assertEqual(res_modal["status_code"], 200)
            self.assertIn("math_trace", res_modal["json"])

            # Step 6: Update user bankroll settings
            res_settings = await client.put("/config/bankroll", json_body={"bankroll": 5000.0, "kelly_fraction": 0.50})
            self.assertEqual(res_settings["status_code"], 200)
            self.assertEqual(client.cache.bankroll, 5000.0)

            # Step 7: Export CSV
            res_export = await client.get("/export/csv")
            self.assertEqual(res_export["status_code"], 200)
            self.assertIn("Player,Team,Market", res_export["text"])

        asyncio.run(run_journey())

    # ==========================================================================
    # Workload 3: Simulated Live Odds Background Refresh
    # ==========================================================================
    def test_w03_simulated_live_odds_background_refresh(self):
        client = MockFastAPIClient()
        with open(ODDS_SAMPLE_CSV_PATH, "r", encoding="utf-8") as f:
            csv_odds = f.read()
        with open(FANTASYPOINTS_CSV_PATH, "r", encoding="utf-8") as f:
            csv_proj = f.read()
        
        asyncio.run(client.post("/api/v1/upload/odds", data=csv_odds))
        asyncio.run(client.post("/api/v1/upload/projections", data=csv_proj))
        
        # Initial EV for Mahomes
        opps_initial = asyncio.run(client.cache.get_opportunities(search="Mahomes"))
        self.assertGreater(len(opps_initial), 0)
        initial_ev = opps_initial[0].blended_ev_percent

        # Background update: Bet365 shifts line odds from -110 (1.909) to +120 (2.20)
        updated_csv = csv_odds.replace("Patrick Mahomes,Over,265.5,-110,1.909", "Patrick Mahomes,Over,265.5,+120,2.200")
        asyncio.run(client.post("/api/v1/upload/odds", data=updated_csv))

        opps_after = asyncio.run(client.cache.get_opportunities(search="Mahomes"))
        after_ev = opps_after[0].blended_ev_percent
        self.assertGreater(after_ev, initial_ev)

    # ==========================================================================
    # Workload 4: Star Player Injury Scratch Recalculation
    # ==========================================================================
    def test_w04_star_player_injury_scratch_recalculation(self):
        client = MockFastAPIClient()
        with open(ODDS_SAMPLE_CSV_PATH, "r", encoding="utf-8") as f:
            csv_odds = f.read()
        with open(FANTASYPOINTS_CSV_PATH, "r", encoding="utf-8") as f:
            csv_proj = f.read()
            
        asyncio.run(client.post("/api/v1/upload/odds", data=csv_odds))
        asyncio.run(client.post("/api/v1/upload/projections", data=csv_proj))

        # Scratch Derrick Henry (replace projection with 0 yds)
        scratched_csv = csv_proj.replace("Derrick Henry,BAL,KC,RB,0.0,0.0,0.0,0.00,0.00,17.5,78.5", "Derrick Henry,BAL,KC,RB,0.0,0.0,0.0,0.00,0.00,0.0,0.0")
        asyncio.run(client.post("/api/v1/upload/projections", data=scratched_csv))

        opps = asyncio.run(client.cache.get_opportunities(search="Henry"))
        if opps:
            # Over EV should be heavily negative or stake 0
            over_opp = next((o for o in opps if o.side.lower() == "over"), None)
            if over_opp:
                self.assertEqual(over_opp.recommended_stake, 0.0)

    # ==========================================================================
    # Workload 5: Concurrent REST API Requests Under Load
    # ==========================================================================
    def test_w05_concurrent_rest_api_requests_under_load(self):
        client = MockFastAPIClient()
        with open(ODDS_SAMPLE_CSV_PATH, "r", encoding="utf-8") as f:
            csv_odds = f.read()
        asyncio.run(client.post("/api/v1/upload/odds", data=csv_odds))

        async def query_task(i: int):
            return await client.get("/api/v1/opportunities", params={"market": "player_pass_yds"})

        async def upload_task(i: int):
            return await client.post("/api/v1/recalculate")

        async def run_concurrent():
            tasks = [query_task(i) for i in range(25)] + [upload_task(i) for i in range(25)]
            results = await asyncio.gather(*tasks)
            self.assertEqual(len(results), 50)
            self.assertTrue(all(r["status_code"] == 200 for r in results))

        asyncio.run(run_concurrent())

    # ==========================================================================
    # Workload 6: Mixed Valid & Corrupted Batch Ingestion
    # ==========================================================================
    def test_w06_mixed_valid_corrupted_batch_ingestion(self):
        mixed_csv = (
            "Player,Team,Opp,Pos,Pass Yds\n"
            "Patrick Mahomes,KC,BAL,QB,270.0\n"
            "Corrupted Row With Missing Values\n"
            "Josh Allen,BUF,NYJ,QB,250.0\n"
            ",,,\n"
            "Lamar Jackson,BAL,KC,QB,220.0"
        )
        projs = FantasyPointsIngestionEngine.parse_csv_text(mixed_csv)
        self.assertEqual(len(projs), 3)

    # ==========================================================================
    # Workload 7: Multi-Bookmaker Sharp Consensus Synthesis
    # ==========================================================================
    def test_w07_multi_bookmaker_sharp_consensus_synthesis(self):
        # Pinnacle: 1.781 / 2.060. Circa: 1.750 / 2.100
        devig_pin = DevigEngine.devig([1.781, 2.060], DevigMethod.SHIN)
        devig_circa = DevigEngine.devig([1.750, 2.100], DevigMethod.SHIN)
        
        # Consensus fair probability average
        p_consensus = (devig_pin.fair_implied_probabilities[0] + devig_circa.fair_implied_probabilities[0]) / 2.0
        self.assertAlmostEqual(p_consensus, 0.540, places=1)

    # ==========================================================================
    # Workload 8: Full Slate Prop Breakdown Modal Integrity
    # ==========================================================================
    def test_w08_full_slate_prop_breakdown_modal_integrity(self):
        client = MockFastAPIClient()
        with open(ODDS_SAMPLE_CSV_PATH, "r", encoding="utf-8") as f:
            csv_odds = f.read()
        asyncio.run(client.post("/api/v1/upload/odds", data=csv_odds))
        asyncio.run(client.cache.recalculate())

        res = asyncio.run(client.get("/api/v1/opportunities/opp_csv_offer_0_bet365_player_pass_yds/breakdown"))
        self.assertEqual(res["status_code"], 200)
        self.assertIn("chart_points", res["json"]["math_trace"])

    # ==========================================================================
    # Workload 9: Rapid Settings Recalculation Benchmark
    # ==========================================================================
    def test_w09_rapid_settings_recalculation_benchmark(self):
        client = MockFastAPIClient()
        with open(ODDS_SAMPLE_CSV_PATH, "r", encoding="utf-8") as f:
            csv_odds = f.read()
        asyncio.run(client.post("/api/v1/upload/odds", data=csv_odds))

        start = time.perf_counter()
        for i in range(20):
            asyncio.run(client.put("/config/bankroll", json_body={"bankroll": 1000.0 + (i * 100)}))
        total_ms = (time.perf_counter() - start) * 1000.0
        
        # Total for 20 recalculations should be well under 100ms
        self.assertLess(total_ms, 100.0)

    # ==========================================================================
    # Workload 10: Empty Cache Graceful Recovery
    # ==========================================================================
    def test_w10_empty_cache_graceful_recovery(self):
        cache = InMemoryCache()
        # Query on empty
        opps_0 = asyncio.run(cache.get_opportunities())
        self.assertEqual(len(opps_0), 0)

        # Add 1 projection
        p = PlayerProjection("p1", "Patrick Mahomes", "patrick mahomes", "KC", PlayerPosition.QB, "BAL", pass_yds=270.0)
        asyncio.run(cache.update_projections([p]))
        asyncio.run(cache.recalculate())
        opps_1 = asyncio.run(cache.get_opportunities())
        self.assertEqual(len(opps_1), 0) # No odds yet

        # Add 1 odds offer
        off = MarketOffer("o1", "e1", "bet365", MarketType.PASSING_YARDS, "Patrick Mahomes", "Over", 265.5, OddsValue.from_american(-110))
        asyncio.run(cache.update_odds([off]))
        asyncio.run(cache.recalculate())
        opps_2 = asyncio.run(cache.get_opportunities())
        self.assertEqual(len(opps_2), 1)


if __name__ == "__main__":
    unittest.main()
