const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const source = fs.readFileSync(path.join(__dirname, '../../static/phase4a.js'), 'utf8');
const helper = source.slice(source.indexOf('  function applyDefensiveAttribution()'), source.indexOf('  function applyDefaultMarketForPosition()'));

function form() {
  const fields = {
    '#manual-decision-source': { value: '' },
    '#manual-analyst': { value: '' },
    '#manual-decision-note': { value: '' },
  };
  const state = {
    editingId: null, automaticDefensiveAttribution: false, attributionManuallyChanged: false,
    category: { value: 'player_prop' }, market: { value: 'tackles_assists' },
    defensiveMarkets: new Set(['tackles_assists', 'solo_tackles', 'sacks', 'defensive_interceptions', 'passes_defended', 'defensive_td']),
    $: selector => fields[selector], syncManualDecisionContext: () => {},
  };
  vm.createContext(state);
  vm.runInContext(helper, state);
  return { state, fields, apply: () => state.applyDefensiveAttribution() };
}

test('new defensive markets default to Justin Varnes', () => {
  const { state, fields, apply } = form();
  for (const market of state.defensiveMarkets) {
    state.market.value = market;
    apply();
    assert.equal(fields['#manual-decision-source'].value, 'analyst');
    assert.equal(fields['#manual-analyst'].value, 'Justin Varnes');
  }
});

test('offensive market clears only the automatic attribution', () => {
  const { state, fields, apply } = form();
  apply();
  state.market.value = 'receiving_yards';
  apply();
  assert.equal(fields['#manual-decision-source'].value, '');
  assert.equal(fields['#manual-analyst'].value, '');
});

test('manual overrides and existing edits are never replaced', () => {
  for (const editing of [false, true]) {
    const { state, fields, apply } = form();
    state.editingId = editing ? 'existing-bet' : null;
    state.attributionManuallyChanged = !editing;
    fields['#manual-decision-source'].value = 'analyst';
    fields['#manual-analyst'].value = 'Other';
    apply();
    state.market.value = 'receiving_yards';
    apply();
    assert.equal(fields['#manual-analyst'].value, 'Other');
  }
});

test('an unattributed existing bet stays unattributed on edit', () => {
  const { state, fields, apply } = form();
  state.editingId = 'existing-bet';
  apply();
  assert.equal(fields['#manual-decision-source'].value, '');
});

test('ordinary offensive entry and previously entered notes are preserved', () => {
  const { state, fields, apply } = form();
  state.market.value = 'rushing_yards';
  apply();
  assert.equal(fields['#manual-decision-source'].value, '');
  state.market.value = 'tackles_assists';
  fields['#manual-decision-note'].value = 'My own research';
  apply();
  assert.equal(fields['#manual-decision-source'].value, '');
  assert.equal(fields['#manual-decision-note'].value, 'My own research');
});
