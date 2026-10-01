"""Validate reviewed team-game receiving tables; preview-only zero recovery.

No web scraping, fuzzy acceptance, or changes to the main research population.
"""
import json
import math
from collections import defaultdict
from pathlib import Path

from app.core.normalizer import PlayerNameNormalizer, TeamNormalizer

BOXSCORES_PATH = Path(__file__).resolve().parents[2] / 'data/research/reviewed_receiving_boxscores.json'


def game_key(row):
    return (int(row['season']), int(row['week']),
            TeamNormalizer.canonical_team(row['team']),
            TeamNormalizer.canonical_team(row['opponent']))


def validate_table(table):
    """Reconcile catches and gross receiving yards, never net passing yards."""
    try:
        if table.get('final') is not True or not table.get('reviewed_at') or not table.get('source_url', '').startswith('https://'):
            return False
        receivers = table['receivers']
        if not isinstance(receivers, list) or not receivers:
            return False
        names = []
        for receiver in receivers:
            name = PlayerNameNormalizer.clean_name(receiver['name'])
            if len(name.split()) < 2:
                return False
            names.append(name)
            for field in ('receptions', 'receiving_yards'):
                value = receiver[field]
                if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not float(value).is_integer():
                    return False
            # Zero-yard and negative-yard catches are valid. Negative catches are not.
            if receiver['receptions'] <= 0:
                return False
        if len(set(names)) != len(names):
            return False
        completions, yards = table['passing_completions'], table['gross_passing_yards']
        if any(isinstance(x, bool) or not isinstance(x, (int, float)) or not math.isfinite(x) or not float(x).is_integer() for x in (completions, yards)):
            return False
        return (completions > 0 and sum(r['receptions'] for r in receivers) == completions
                and sum(r['receiving_yards'] for r in receivers) == yards)
    except (KeyError, TypeError, ValueError):
        return False


class ReviewedReceivingRecovery:
    def __init__(self, path=BOXSCORES_PATH):
        self.tables = defaultdict(list)
        self.warnings = []
        try:
            tables = json.loads(Path(path).read_text(encoding='utf-8'))
            if not isinstance(tables, list):
                raise ValueError('Expected a list of reviewed team-game tables.')
            for table in tables:
                try:
                    self.tables[game_key(table)].append(table)
                except (KeyError, TypeError, ValueError):
                    self.warnings.append('Reviewed receiving table has invalid game identity; ignored.')
        except FileNotFoundError:
            pass
        except (OSError, ValueError):
            self.warnings.append('Reviewed receiving tables unavailable or invalid; no table-based recovery.')

    def check(self, row):
        if row.get('market') not in ('receiving_yards', 'receptions'):
            return None
        matches = self.tables.get(game_key(row), [])
        if not matches:
            return None
        if len(matches) != 1 or not validate_table(matches[0]):
            return {'verified_zero': False, 'detail': 'Receiving table is duplicate, incomplete, or unreconciled; unresolved.'}
        table = matches[0]
        name = PlayerNameNormalizer.clean_name(row['player_name'])
        parts = name.split()
        if len(parts) < 2:
            return {'verified_zero': False, 'detail': 'Player name is incomplete; unresolved.'}
        # A same-surname entry is a possible match, not evidence of absence.
        # Abbreviations, suffixes, and multi-part surnames must never produce a false zero.
        surname = parts[-1]
        if any(surname == PlayerNameNormalizer.clean_name(r['name']).split()[-1] for r in table['receivers']):
            return {'verified_zero': False, 'detail': 'Player or same-surname receiver is listed; do not infer zero from absence.'}
        return {'verified_zero': True, 'source_url': table['source_url'], 'reviewed_at': table['reviewed_at'],
                'detail': 'Played offensive snaps and absent from a reviewed final receiving table reconciled to passing totals. Preview-only receiving zero.'}
