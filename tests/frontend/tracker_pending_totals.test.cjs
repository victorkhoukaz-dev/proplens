const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const source = fs.readFileSync(path.join(__dirname, '../../static/phase2a.js'), 'utf8');
const start = source.indexOf('  function summarizeActivity(');
const end = source.indexOf('\n  function ', start + 1);
const context = {};
vm.createContext(context);
vm.runInContext(source.slice(start, end), context);
const activity = [
  { status: 'pending', bet_type: 'cash', stake: 5 },
  { status: 'won', bet_type: 'cash', stake: 10, profit: 8.6 },
  { status: 'pending', bet_type: 'bonus', stake: 4 },
];
test('pending stakes always contribute to the selected view', () => {
  const summary = context.summarizeActivity(activity);
  assert.equal(summary.cash_wagered, 15);
  assert.equal(summary.bonus_value_used, 4);
  assert.equal(summary.pending_cash_at_risk, 5);
  assert.equal(summary.total_profit, 8.6);
  assert.equal(summary.cash_roi_pct, 86);
});
test('settled view excludes pending stakes and exposure', () => {
  const summary = context.summarizeActivity(activity.filter(bet => bet.status !== 'pending'));
  assert.equal(summary.cash_wagered, 10);
  assert.equal(summary.bonus_value_used, 0);
  assert.equal(summary.pending_cash_at_risk, 0);
});
