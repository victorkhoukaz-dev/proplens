import json

from app.services.research_participation import ResearchParticipationService

SNAPS = 'season,week,game_type,player,team,opponent,offense_snaps\n2026,2,REG,Test Player,PHI,DAL,12\n'


def setup_service(tmp_path, monkeypatch, classification='played', snaps=SNAPS):
    path = tmp_path / 'evidence.json'
    path.write_text(json.dumps([{'season':2026,'week':2,'player_name':'Test Player','team':'PHI','opponent':'DAL','classification':classification,'zero_markets':['receiving_yards'],'sources':['https://example.com/final'],'reviewed_at':'2026-09-30'}]))
    service = ResearchParticipationService(tmp_path, path)
    monkeypatch.setattr(service, '_snap_content', lambda season, refresh: {'content':snaps,'url':'https://example.com/snaps','fetched_at':'now','used_cache':True,'warning':''})
    return service


def row(**changes):
    return {'season':2026,'week':2,'player_name':'Test Player','team':'PHI','opponent':'DAL','stage':'selected','reason':'no_player_stat_record','market':'receiving_yards','game_completed':True,**changes}


def status(service, record=None):
    return service.preview([record or row()])['records'][0]['participation_preview']['status']


def test_verified_zero_is_preview_only_and_input_unchanged(tmp_path, monkeypatch):
    service = setup_service(tmp_path, monkeypatch)
    original = row()
    assert status(service, original) == 'verified_played_zero'
    assert 'actual_stat' not in original
    assert status(service, row(market='rushing_yards')) == 'unresolved'


def test_positive_snaps_alone_or_wrong_game_never_zero(tmp_path, monkeypatch):
    service = setup_service(tmp_path, monkeypatch)
    assert status(service, row(opponent='NYG')) == 'unresolved'
    service.evidence_path.write_text('[]')
    assert status(service) == 'unresolved'


def test_unfinished_ambiguous_and_wrong_stage(tmp_path, monkeypatch):
    service = setup_service(tmp_path, monkeypatch)
    assert status(service, row(game_completed=False)) == 'unresolved'
    assert status(service, row(reason='multiple_exact_stat_matches')) == 'unresolved'
    assert status(service, row(stage='import')) == 'not_checked'
    service = setup_service(tmp_path, monkeypatch, snaps=SNAPS + SNAPS.split('\n')[1] + '\n')
    assert status(service) == 'unresolved'


def test_inactive_and_conflicting_evidence(tmp_path, monkeypatch):
    service = setup_service(tmp_path, monkeypatch, classification='inactive', snaps=SNAPS.split('\n')[0] + '\n')
    assert status(service) == 'verified_nonparticipant'
    service = setup_service(tmp_path, monkeypatch, classification='inactive')
    assert status(service) == 'unresolved'


def test_missing_source_never_zero(tmp_path, monkeypatch):
    service = setup_service(tmp_path, monkeypatch)
    def unavailable(*args):
        raise ValueError('Unavailable')
    monkeypatch.setattr(service, '_snap_content', unavailable)
    result = service.preview([row()])
    assert result['participation']['warnings']
    assert result['records'][0]['participation_preview']['status'] == 'unresolved'


def test_schedule_requires_final_scores():
    from app.services.model_research import ModelResearchService
    header = 'season,week,game_type,gameday,gametime,home_team,away_team,home_score,away_score\n'
    assert ModelResearchService._schedule_rows(header + '2026,2,REG,2026-09-20,13:00,PHI,DAL,0,10\n')[0]['completed']
    assert not ModelResearchService._schedule_rows(header + '2026,2,REG,2026-09-20,13:00,PHI,DAL,,\n')[0]['completed']


def test_reviewed_batch_two_is_game_and_market_specific(tmp_path, monkeypatch):
    from app.services.research_participation import EVIDENCE_PATH, identity
    facts = json.loads(EVIDENCE_PATH.read_text(encoding='utf-8'))
    assert len({identity(fact) for fact in facts}) == len(facts)
    batch = [fact for fact in facts if fact['player_name'] in
             {'Jordan Whittington', 'Jack Bech', 'Jonnu Smith'}]
    assert len(batch) == 3
    for fact in batch:
        content = 'season,week,game_type,player,team,opponent,offense_snaps\n'
        content += f"2026,{fact['week']},REG,{fact['player_name']},{fact['team']},{fact['opponent']},11\n"
        service = ResearchParticipationService(tmp_path, EVIDENCE_PATH)
        monkeypatch.setattr(service, '_snap_content', lambda season, refresh, content=content:
                            {'content':content,'url':'https://example.com/snaps','fetched_at':'now','used_cache':True,'warning':''})
        record = row(week=fact['week'], player_name=fact['player_name'], team=fact['team'], opponent=fact['opponent'])
        assert status(service, record) == 'verified_played_zero'
        assert status(service, {**record, 'market':'receptions'}) == 'verified_played_zero'
        assert status(service, {**record, 'market':'rushing_yards'}) == 'unresolved'
        assert status(service, {**record, 'week':4}) == 'unresolved'
