import copy

from scripts.research.bulk_participation_probe import reconcile, reviewed_agreement


def fixtures():
    team = dict(season='2026',week='1',team='CIN',opponent_team='TB',game_id='2026_01_TB_CIN',
                completions='3',passing_yards='19',receptions='3',receiving_yards='19',carries='1',rushing_yards='-2')
    player = {**team,'player_id':'gsis-1','player_display_name':'Drew Sample'}
    table = dict(season=2026,week=1,team='CIN',opponent='TB',final=True,reviewed_at='now',
                 source_url='https://example.com/final',passing_completions=3,gross_passing_yards=19,
                 receivers=[dict(name='D. Sample',receptions=3,receiving_yards=19)])
    return team, [player], table


def test_complete_totals_and_literal_source_initials():
    team, players, table = fixtures()
    assert reconcile(team, players)
    assert reviewed_agreement(table, team, players)


def test_missing_or_duplicate_identity_not_recoverable():
    team, players, _ = fixtures()
    assert not reconcile(team, players + players)
    players[0]['player_id'] = ''
    assert not reconcile(team, players)


def test_partial_wrong_game_or_invalid_stats_rejected():
    team, players, _ = fixtures()
    for change in ({'receptions':'2'},{'receiving_yards':''},{'carries':'nan'},
                   {'game_id':'wrong'}, {'opponent_team':'NYG'}):
        assert not reconcile(team, [{**players[0],**change}])
    assert not reconcile(team, [])


def test_negative_yards_preserved_but_negative_attempt_counts_rejected():
    team, players, _ = fixtures()
    assert reconcile(team, players)
    team['carries'] = players[0]['carries'] = '-1'
    assert not reconcile(team, players)


def test_team_passing_receiving_must_agree_even_if_player_sums_match():
    team, players, _ = fixtures()
    team['completions'] = players[0]['completions'] = '4'
    assert not reconcile(team, players)


def test_reviewed_table_collision_or_stat_disagreement_rejected():
    team, players, table = fixtures()
    broken = copy.deepcopy(table)
    broken['receivers'][0]['name'] = 'A. Sample'
    assert not reviewed_agreement(broken,team,players)
    broken = copy.deepcopy(table)
    broken['receivers'][0]['receiving_yards'] = 18
    assert not reviewed_agreement(broken,team,players)
