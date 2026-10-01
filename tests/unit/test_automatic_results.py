from copy import deepcopy
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from app.api import routes
from app.db.bet_tracker_store import bet_tracker_store
from app.main import app
from app.services import automatic_results as auto
from app.services.result_preview import ResultPreviewService


@pytest.fixture
def setup(tmp_path, monkeypatch):
    monkeypatch.setattr(bet_tracker_store, 'path', tmp_path / 'bets.json')
    schedule = 'season,week,home_team,away_team,gameday,gametime,home_score,away_score\n2025,1,PHI,DAL,2025-09-07,13:00,24,20\n'
    monkeypatch.setattr(auto.model_research_service, '_schedule_content', lambda refresh: (schedule, 'schedule-time', False))
    bet = bet_tracker_store.create({
        'player_name': 'Saquon Barkley', 'market': 'rushing_yards', 'side_label': 'Over',
        'line': 55.5, 'stake': 5, 'decimal_odds': 1.86, 'bet_type': 'cash',
        'result_identity': {'status': 'ready', 'season': 2025, 'week': 1,
                            'player_key': 'saquon barkley', 'team': 'PHI', 'opponent': 'DAL'},
    })
    report = {
        'preview_only': True, 'sources': [{'season': 2025, 'fetched_at': 'stats-time', 'used_cache': False}],
        'proposals': [{'bet_id': bet['id'], 'status': 'proposal', 'proposed_result': 'won',
                       'actual_stat': 84, 'stat_label': 'rushing yards', 'participation_confirmed': True}],
        'parlays': [], 'checked_straight': 1, 'checked_parlays': 0,
    }
    return bet, report


def test_settlement_preserves_financials_and_saves_evidence(setup):
    bet, report = setup
    result = auto.settle_eligible([bet], report)
    assert result['won'] == 1
    saved = bet_tracker_store.list()[0]
    assert saved['profit'] == 4.3
    assert saved['stake'] == bet['stake']
    assert saved['settlement_evidence']['mode'] == 'automatic'
    assert saved['settlement_evidence']['game_completed'] is True
    assert saved['settlement_evidence']['schedule_fetched_at'] == 'schedule-time'
    assert saved['settlement_history'][-1]['source'] == 'automatic_result_check'
    assert auto.settle_eligible(bet_tracker_store.list(), report)['settled'] == []


@pytest.mark.parametrize('changes', [
    {'market': 'anytime_td'}, {'market': 'tackles_assists'}, {'market': 'passing_tds'},
    {'line': 55}, {'line': float('nan')}, {'status': 'won'}, {'status': 'cashed_out'},
    {'category': 'game_bet'}, {'result_identity': None}, {'safety_net': {'enabled': True}},
    {'profit_boost_pct': 25}, {'side_label': 'Yes'}, {'stake': 0},
])
def test_excluded_records_never_settle(setup, changes):
    bet, report = setup
    assert auto.settle_eligible([{**bet, **changes}], report)['settled'] == []
    assert bet_tracker_store.list()[0]['status'] == 'pending'


@pytest.mark.parametrize('case', ['unfinished', 'wrong_week', 'wrong_game', 'duplicate', 'future', 'cached_schedule', 'missing_schedule'])
def test_completion_safeguards(setup, monkeypatch, case):
    bet, report = setup
    game = {'season': 2025, 'week': 1, 'home': 'PHI', 'away': 'DAL', 'completed': True,
            'kickoff': datetime(2025, 9, 7, tzinfo=timezone.utc)}
    if case == 'unfinished': game['completed'] = False
    if case == 'wrong_week': game['week'] = 2
    if case == 'wrong_game': game['home'] = 'BUF'
    if case == 'future': game['kickoff'] = datetime(2099, 1, 1, tzinfo=timezone.utc)
    if case == 'cached_schedule':
        monkeypatch.setattr(auto.model_research_service, '_schedule_content', lambda refresh: ('', '', True))
    if case == 'missing_schedule':
        def fail(refresh): raise RuntimeError('offline')
        monkeypatch.setattr(auto.model_research_service, '_schedule_content', fail)
    monkeypatch.setattr(auto.model_research_service, '_schedule_rows', lambda content: [game, game] if case == 'duplicate' else [game])
    assert auto.settle_eligible([bet], report)['settled'] == []
    assert bet_tracker_store.list()[0]['status'] == 'pending'


@pytest.mark.parametrize('case', ['stale_stats', 'missing_player', 'missing_stat', 'nonparticipant', 'invalid_stat', 'push'])
def test_stat_safeguards(setup, case):
    bet, report = setup
    if case == 'stale_stats': report['sources'][0]['used_cache'] = True
    if case == 'missing_player': report['proposals'][0]['status'] = 'player_review'
    if case == 'missing_stat': report['proposals'][0]['status'] = 'player_review'
    if case == 'nonparticipant': report['proposals'][0]['participation_confirmed'] = False
    if case == 'invalid_stat': report['proposals'][0]['actual_stat'] = float('nan')
    if case == 'push': report['proposals'][0]['proposed_result'] = 'push'
    assert auto.settle_eligible([bet], report)['settled'] == []
    assert bet_tracker_store.list()[0]['status'] == 'pending'


def test_concurrent_edit_is_not_overwritten(setup):
    bet, report = setup
    bet_tracker_store.update(bet['id'], {'line': 100.5})
    assert auto.settle_eligible([bet], report)['settled'] == []
    assert bet_tracker_store.list()[0]['line'] == 100.5
    assert bet_tracker_store.list()[0]['status'] == 'pending'


@pytest.mark.parametrize('bet_type,expected_profit', [('cash', -5), ('bonus', 0)])
def test_losing_cash_and_bonus_accounting(setup, bet_type, expected_profit):
    bet, report = setup
    bet = bet_tracker_store.update(bet['id'], {'bet_type': bet_type})
    report['proposals'][0]['proposed_result'] = 'lost'
    assert auto.settle_eligible([bet], report)['lost'] == 1
    assert bet_tracker_store.list()[0]['profit'] == expected_profit


def test_endpoint_requires_opt_in_and_leaves_parlays_manual(setup, monkeypatch):
    bet, report = setup
    report['parlays'] = [{'parlay_id': 'parlay-1', 'status': 'proposal', 'proposed_result': 'won'}]
    monkeypatch.setattr(routes, 'preview_all_tracked_results', lambda: deepcopy(report))
    client = TestClient(app)
    assert client.post('/api/tracker/results/check', json={}).json()['preview_only'] is True
    assert bet_tracker_store.list()[0]['status'] == 'pending'
    response = client.post('/api/tracker/results/check', json={'auto_settle': True})
    assert response.status_code == 200
    assert response.json()['automatic']['won'] == 1
    assert response.json()['proposals'] == []
    assert response.json()['parlays'] == report['parlays']


def test_participation_requires_recorded_activity():
    content = 'season,week,player_display_name,team,opponent_team,rushing_yards,carries,receiving_yards,receptions,targets\n2025,1,Example Player,PHI,DAL,0,0,0,0,0\n'
    assert ResultPreviewService._rows(content)[0]['participation_confirmed'] is False
    assert ResultPreviewService._rows(content.replace(',0,0,0,0,0', ',0,0,0,0,1'))[0]['participation_confirmed'] is True


def test_manual_correction_keeps_audit_but_clears_active_auto_label(setup):
    bet, report = setup
    auto.settle_eligible([bet], report)
    corrected = bet_tracker_store.update(bet['id'], {'status': 'pending'})
    assert corrected['profit'] is None
    assert corrected['settlement_evidence'] is None
    assert corrected['settlement_history'][0]['evidence']['mode'] == 'automatic'
    assert corrected['settlement_history'][-1]['source'] == 'manual_correction'
