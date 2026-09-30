from scripts.research.sgp_research_report import build_pairs, report_directory


def test_report_location_and_legacy_entry_point():
    from datetime import datetime, timezone
    from scripts.sgp_research_report import build_pairs as legacy
    assert legacy is build_pairs
    output = report_directory(2026, 3, datetime(2026, 9, 30, tzinfo=timezone.utc))
    assert output.parts[-5:] == ('research', '2026', 'sgp-correlation', 'reports', 'week-03_20260930T000000000000Z')


def test_pairing_checks_final_games_market_position_and_participation():
    schedule = "season,week,game_type,home_team,away_team,home_score,away_score\n2026,1,REG,HOU,BAL,20,21\n2026,1,REG,KC,DEN,,\n"
    stats = "season,week,season_type,team,opponent_team,position,player_display_name,attempts\n2026,1,REG,HST,BLT,QB,Starter,20\n2026,1,REG,HOU,BAL,QB,Backup,2\n"
    def player(name, position, market, team="HOU", opponent="BAL"):
        return dict(season=2026, week=1, team=team, opponent=opponent, player_name=name,
                    position=position, market=market, projection_mean=0, kickoff="test")
    records = [player("Starter", "QB", "passing_yards"), player("Receiver", "WR", "receiving_yards"),
               player("Tight end", "TE", "receiving_yards"), player("Opponent", "WR", "receiving_yards", "BAL", "HOU"),
               player("Pending QB", "QB", "passing_yards", "KC", "DEN"), player("Pending WR", "WR", "receiving_yards", "KC", "DEN")]
    pairs, excluded = build_pairs(records, schedule, stats, 2026, 1)
    assert len(pairs) == 1
    assert pairs[0]["wr"]["player_name"] == "Receiver"
    assert pairs[0]["flags"] == ["zero_projection", "multiple_QBs_attempted_passes"]
    assert excluded == {"matched_player_game_not_confirmed_final": 2}
