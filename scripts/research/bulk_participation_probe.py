"""Bulk source validation only; does not change app preview or accuracy metrics."""
import argparse
import csv
import hashlib
import io
import json
import math
import urllib.request
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

from app.core.normalizer import PlayerNameNormalizer, TeamNormalizer
from app.db.result_cache_store import result_cache_store
from app.services.model_research import model_research_service
from app.services.research_participation import ResearchParticipationService, identity
from app.services.research_receiving_recovery import BOXSCORES_PATH, game_key, validate_table

TEAM_URL = 'https://github.com/nflverse/nflverse-data/releases/download/stats_team/stats_team_week_{season}.csv'
MARKETS = {'receiving_yards':'receiving_yards', 'receptions':'receptions',
           'rushing_yards':'rushing_yards', 'rushing_attempts':'carries'}
FIELDS = ('completions', 'passing_yards', 'receptions', 'receiving_yards', 'carries', 'rushing_yards')


def number(value):
    value = float(value)
    if not math.isfinite(value) or not value.is_integer():
        raise ValueError('Missing or invalid integer stat')
    return int(value)


def key(raw):
    return game_key({**raw, 'opponent':raw['opponent_team']})


def reconcile(team, players):
    """Detect truncated/duplicate/context-mismatched player tables before inferring absence."""
    try:
        if not players or any(p['game_id'] != team['game_id'] or key(p) != key(team) for p in players):
            return False
        ids = [p['player_id'] for p in players]
        names = [PlayerNameNormalizer.clean_name(p['player_display_name']) for p in players]
        if any(not x for x in ids + names) or len(set(ids)) != len(ids) or len(set(names)) != len(names):
            return False
        for field in FIELDS:
            if sum(number(p[field]) for p in players) != number(team[field]):
                return False
        return (number(team['receptions']) == number(team['completions'])
                and number(team['receiving_yards']) == number(team['passing_yards'])
                and number(team['receptions']) >= 0 and number(team['carries']) >= 0
                and all(number(p['receptions']) >= 0 and number(p['carries']) >= 0 for p in players))
    except (KeyError, TypeError, ValueError):
        return False


def reviewed_agreement(table, team, players):
    if not validate_table(table) or not reconcile(team, players):
        return False
    productive = [p for p in players if number(p['receptions']) > 0]
    if len(productive) != len(table['receivers']):
        return False
    for receiver in table['receivers']:
        parts = PlayerNameNormalizer.clean_name(receiver['name']).split()
        matches = [p for p in productive if
                   PlayerNameNormalizer.clean_name(p['player_display_name']).split()[-1] == parts[-1]
                   and p['player_display_name'].strip()[0].lower() == receiver['name'].strip()[0].lower()]
        if len(matches) != 1 or any(number(matches[0][f]) != receiver[f] for f in ('receptions','receiving_yards')):
            return False
    return (number(team['completions']) == table['passing_completions']
            and number(team['passing_yards']) == table['gross_passing_yards'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--season', type=int, required=True)
    parser.add_argument('--through-week', type=int, required=True)
    args = parser.parse_args()
    if not 1 <= args.through_week <= 18:
        parser.error('NFL week must be 1 through 18.')
    cached = result_cache_store.get_nflverse_season(args.season)
    if not cached or not result_cache_store.get_nflverse_schedule():
        raise SystemExit('Saved player stats and schedule required; no app-cache refresh in this probe.')
    url = TEAM_URL.format(season=args.season)
    with urllib.request.urlopen(urllib.request.Request(url, headers={'User-Agent':'PropLens-BulkResearch/1.0'}), timeout=25) as response:
        team_content = response.read().decode('utf-8-sig')
    now = datetime.now(timezone.utc)
    groups, teams = defaultdict(list), defaultdict(list)
    for content, target in ((cached['content'],groups),(team_content,teams)):
        for raw in csv.DictReader(io.StringIO(content)):
            if raw['season_type'] == 'REG' and int(raw['season']) == args.season and 1 <= int(raw['week']) <= args.through_week:
                target[key(raw)].append(raw)
    valid = {k for k, rows in teams.items() if len(rows) == 1 and reconcile(rows[0], groups[k])}
    reviewed = json.loads(BOXSCORES_PATH.read_text()) if BOXSCORES_PATH.exists() else []
    comparisons = []
    for table in reviewed:
        k = game_key(table)
        if k in teams:
            comparisons.append({'game':list(k), 'agrees':len(teams[k]) == 1 and reviewed_agreement(table,teams[k][0],groups[k])})
    report = model_research_service.report(season=args.season, through_week=args.through_week, include_unmatched=True)
    service = ResearchParticipationService()
    current = service.preview(report['unmatched_records'])
    snap_source = service._snap_content(args.season, refresh=False)
    snaps = defaultdict(list)
    for raw in csv.DictReader(io.StringIO(snap_source['content'])):
        if raw['game_type'] == 'REG':
            try:
                snaps[identity(raw)].append({f:number(raw[f]) for f in ('offense_snaps','defense_snaps','st_snaps')})
            except (KeyError, ValueError):
                continue
    rows = []
    for record in current['records']:
        if record['stage'] != 'selected':
            continue
        outcome = 'existing_verified'
        if record['participation_preview']['status'] == 'unresolved':
            outcome = 'unsupported_or_unsafe_stat_reason'
            if record['market'] in MARKETS and record['reason'] == 'no_player_stat_record' and record.get('game_completed'):
                matches = snaps.get(identity(record), [])
                k = game_key(record)
                if len(matches) != 1:
                    outcome = 'no_unique_participation_record'
                elif matches[0]['offense_snaps'] <= 0:
                    outcome = 'no_offensive_snaps_other_participation' if any(v > 0 for v in matches[0].values()) else 'no_verified_positive_snaps'
                elif k not in valid:
                    outcome = 'team_totals_unreconciled_or_missing'
                elif any(PlayerNameNormalizer.clean_name(p['player_display_name']).split()[-1] == identity(record)[-1].split()[-1] for p in groups[k] if number(p['receptions' if record['market'] in ('receiving_yards','receptions') else 'carries']) > 0):
                    outcome = 'possible_productive_player_identity'
                elif 'Conflicting' in record['participation_preview']['detail']:
                    outcome = 'conflicting_evidence'
                else:
                    outcome = 'bulk_zero_candidate'
        rows.append({**record, 'bulk_probe_status':outcome})
    summary = dict(Counter(r['bulk_probe_status'] for r in rows))
    payload = {'scope':{'season':args.season,'through_week':args.through_week}, 'generated_at':now.isoformat(),
               'preview_only':True, 'main_metrics_unchanged':True, 'summary':summary,
               'team_games':len(teams),'reconciled_team_games':len(valid),
               'reviewed_source_comparisons':comparisons,
               'candidate_by_market':dict(Counter(r['market'] for r in rows if r['bulk_probe_status']=='bulk_zero_candidate')),
               'sources':{'team_url':url,'team_fetched_at':now.isoformat(),'player_fetched_at':cached['fetched_at'],
                          'snap_fetched_at':snap_source['fetched_at'],
                          'team_sha256':hashlib.sha256(team_content.encode()).hexdigest(),
                          'player_sha256':hashlib.sha256(cached['content'].encode()).hexdigest()},
               'limitations':['Team/player stats share nflverse upstream: reconciliation is not independent source confirmation.',
                              'Candidates are not accepted zeros or included in app metrics.',
                              'No offensive snaps does not establish nonparticipation.'], 'records':rows}
    output = Path(__file__).resolve().parents[2] / 'research' / str(args.season) / 'calibration' / 'reports' / f"through-week-{args.through_week:02d}_bulk-probe_{now.strftime('%Y%m%dT%H%M%S%fZ')}"
    output.mkdir(parents=True, exist_ok=False)
    (output/'report.json').write_text(json.dumps(payload,indent=2),encoding='utf-8')
    (output/'team-source.json').write_text(json.dumps({'url':url,'fetched_at':now.isoformat(),'content':team_content}),encoding='utf-8')
    print(json.dumps({'output':str(output),'summary':summary,'team_games':len(teams),'reconciled_team_games':len(valid),
                      'reviewed_comparisons':comparisons,'candidate_by_market':payload['candidate_by_market']}))


if __name__ == '__main__':
    main()
