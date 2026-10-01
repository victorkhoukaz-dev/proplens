import copy
import json

import pytest

from app.services.research_participation import ResearchParticipationService
from app.services.research_receiving_recovery import ReviewedReceivingRecovery, validate_table


def table():
    return dict(season=2026, week=2, team='PHI', opponent='DAL', final=True,
                source_url='https://example.com/final', reviewed_at='2026-09-30',
                passing_completions=3, gross_passing_yards=10,
                receivers=[dict(name='A. Receiver', receptions=1, receiving_yards=10),
                           dict(name='B. Corum', receptions=2, receiving_yards=0)])


def row(**changes):
    return dict(season=2026, week=2, team='PHI', opponent='DAL', player_name='Test Player',
                market='receiving_yards', stage='selected', reason='no_player_stat_record',
                game_completed=True, **changes)


def service(tmp_path, monkeypatch, tables=None, snaps=12, facts=None):
    box = tmp_path / 'box.json'
    box.write_text(json.dumps([table()] if tables is None else tables))
    evidence = tmp_path / 'evidence.json'
    evidence.write_text(json.dumps(facts or []))
    result = ResearchParticipationService(tmp_path, evidence, box)
    content = f'season,week,game_type,player,team,opponent,offense_snaps\n2026,2,REG,Test Player,PHI,DAL,{snaps}\n'
    monkeypatch.setattr(result, '_snap_content', lambda *args: dict(content=content, url='https://example.com/snaps', fetched_at='now', used_cache=True, warning=''))
    return result


def preview(service, record=None):
    return service.preview([record or row()])['records'][0]['participation_preview']


def test_reconciled_table_recovers_two_markets_without_mutating_record(tmp_path, monkeypatch):
    instance = service(tmp_path, monkeypatch)
    original = row()
    saved = copy.deepcopy(original)
    for market in ('receiving_yards', 'receptions'):
        result = preview(instance, {**original, 'market':market})
        assert result['status'] == 'verified_played_zero'
        assert result['method'] == 'reviewed_receiving_table'
        assert result['actual_stat'] == 0
    assert original == saved


@pytest.mark.parametrize('change', [
    {'game_completed':False}, {'week':3}, {'opponent':'NYG'}, {'market':'rushing_yards'},
    {'stage':'import'}, {'reason':'possible_name_mismatch'},
])
def test_recovery_requires_safe_context(tmp_path, monkeypatch, change):
    assert preview(service(tmp_path, monkeypatch), {**row(), **change})['status'] != 'verified_played_zero'


@pytest.mark.parametrize('snaps', [0, -1, 'nan'])
def test_absence_without_positive_snaps_never_zero(tmp_path, monkeypatch, snaps):
    assert preview(service(tmp_path, monkeypatch, snaps=snaps))['status'] == 'unresolved'


def test_zero_yards_with_two_catches_and_abbreviated_names_never_absence(tmp_path):
    path = tmp_path / 'table.json'
    path.write_text(json.dumps([table()]))
    check = ReviewedReceivingRecovery(path)
    assert validate_table(table())
    assert not check.check({**row(), 'player_name':'Blake Corum'})['verified_zero']
    assert not check.check({**row(), 'player_name':'Another Receiver'})['verified_zero']


@pytest.mark.parametrize('change', [
    {'final':False}, {'passing_completions':4}, {'gross_passing_yards':9},
    {'receivers':[]}, {'source_url':''}, {'reviewed_at':''},
    {'receivers':[dict(name='Unknown', receptions=3, receiving_yards=10)]},
    {'passing_completions':True},
])
def test_incomplete_or_invalid_tables_rejected(tmp_path, monkeypatch, change):
    broken = {**table(), **change}
    assert not validate_table(broken)
    assert preview(service(tmp_path, monkeypatch, tables=[broken]))['status'] == 'unresolved'


def test_duplicate_tables_rejected(tmp_path, monkeypatch):
    assert preview(service(tmp_path, monkeypatch, tables=[table(), table()]))['status'] == 'unresolved'


def test_inactive_evidence_conflict_blocks_table_zero(tmp_path, monkeypatch):
    fact = {**row(), 'classification':'inactive', 'sources':['https://example.com/inactive'], 'reviewed_at':'now'}
    result = preview(service(tmp_path, monkeypatch, facts=[fact]))
    assert result['status'] == 'unresolved'


def test_negative_receiving_yards_can_reconcile():
    source = table()
    source['receivers'][0]['receiving_yards'] = -2
    source['gross_passing_yards'] = -2
    assert validate_table(source)


def test_invalid_source_file_warns_and_does_not_recover(tmp_path):
    path = tmp_path / 'bad.json'
    path.write_text('{}')
    recovery = ReviewedReceivingRecovery(path)
    assert recovery.warnings
    assert recovery.check(row()) is None
