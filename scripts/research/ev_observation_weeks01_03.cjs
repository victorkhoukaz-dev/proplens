// Read-only descriptive audit. One record per settled straight, no tracker writes.
const fs = require('fs');
const { dataPath, emit } = require('./report_output.cjs');
const crypto = require('crypto');
const paths = ['data/tracked_bets.json', 'data/result_cache.json'];
const raw = paths.map(p => fs.readFileSync(dataPath(p)));
const bets = JSON.parse(raw[0]).bets;
const schedule = JSON.parse(raw[1]).nflverse_schedule.content;
function csv(text) {
  const rows = []; let row = [], cell = '', quoted = false;
  for (let i = 0; i < text.length; i++) {
    const c = text[i];
    if (c === '"') { if (quoted && text[i + 1] === '"') { cell += '"'; i++; } else quoted = !quoted; }
    else if (!quoted && (c === ',' || c === '\n')) { row.push(cell.replace(/\r$/, '')); cell = ''; if (c === '\n') { rows.push(row); row = []; } }
    else cell += c;
  }
  if (cell || row.length) { row.push(cell); rows.push(row); }
  const head = rows.shift(); return rows.map(r => Object.fromEntries(head.map((k, i) => [k, r[i]])));
}
const norm = t => ({ LA: 'LAR', BLT: 'BAL', HST: 'HOU', ARZ: 'ARI', CLV: 'CLE' }[t] || t);
const key = (w, a, b) => [w, ...[norm(a), norm(b)].sort()].join('|');
const games = new Map();
for (const g of csv(schedule)) {
  if (+g.season !== 2026 || ![1, 2, 3].includes(+g.week) || !g.gametime) continue;
  // NFL schedule time is Eastern; all three September weeks are UTC-04:00.
  games.set(key(+g.week, g.home_team, g.away_team), Date.parse(g.gameday + 'T' + g.gametime + '-04:00'));
}
const supported = new Set(['receiving_yards', 'rushing_yards', 'passing_yards', 'receptions', 'rushing_attempts', 'anytime_td']);
const exclusions = {}; const exclude = k => exclusions[k] = (exclusions[k] || 0) + 1;
const records = []; let postKickoffSnapshots = 0;
for (const t of bets) {
  const ident = t.result_identity || {}; const week = t.week ?? ident.week;
  if ((t.season ?? ident.season) !== 2026 || ![1, 2, 3].includes(week)) continue;
  if (!['won', 'lost'].includes(t.status)) { exclude('not_win_or_loss'); continue; }
  if (!supported.has(t.market)) { exclude('unsupported_or_tracking_only_market'); continue; }
  const kickoff = games.get(key(week, t.team || ident.team, t.opponent || ident.opponent));
  if (!Number.isFinite(kickoff)) { exclude('missing_schedule_match'); continue; }
  const snaps = [];
  if (Number.isFinite(t.expected_value_pct)) snaps.push({ ev: t.expected_value_pct, at: t.created_at, kind: 'original' });
  for (const s of [...(t.later_evaluations || []), ...(t.evaluation_refreshes || [])]) {
    if (Number.isFinite(s.value?.expected_value_pct)) snaps.push({ ev: s.value.expected_value_pct, at: s.evaluated_at, kind: s.kind });
  }
  const eligible = snaps.filter(s => Number.isFinite(Date.parse(s.at)) && Date.parse(s.at) < kickoff).sort((a, b) => Date.parse(a.at) - Date.parse(b.at));
  postKickoffSnapshots += snaps.filter(s => Date.parse(s.at) >= kickoff).length;
  if (!eligible.length) { exclude('no_saved_evaluation_before_kickoff'); continue; }
  records.push({ id: t.id, week, market: t.market, name: t.player_name, funding: t.bet_type, stake: t.stake, profit: t.profit, status: t.status, original: eligible.find(s => s.kind === 'original') || null, first: eligible[0], latest: eligible.at(-1), analyst: t.decision_context?.analyst || null });
}
const round = x => Math.round(x * 100) / 100;
function stats(rows) { const stake = rows.reduce((s, t) => s + t.stake, 0), profit = rows.reduce((s, t) => s + t.profit, 0), wins = rows.filter(t => t.status === 'won').length; return { n: rows.length, wins, losses: rows.length - wins, winRate: rows.length ? round(wins / rows.length * 100) : null, stake: round(stake), profit: round(profit), roi: stake ? round(profit / stake * 100) : null }; }
function compare(rows, mode = 'latest') { const a = rows.filter(t => t[mode]); return { positive: stats(a.filter(t => t[mode].ev > 0)), negative: stats(a.filter(t => t[mode].ev < 0)), zero: stats(a.filter(t => t[mode].ev === 0)) }; }
const cash = records.filter(t => t.funding === 'cash');
const nonTD = cash.filter(t => t.market !== 'anytime_td');
const output = { sources: paths.map((p, i) => ({ path: p, sha256: crypto.createHash('sha256').update(raw[i]).digest('hex') })), exclusions, postKickoffSnapshots, funding: { cash: cash.length, bonus: records.filter(t => t.funding === 'bonus').length }, nonTD: compare(nonTD), td: compare(cash.filter(t => t.market === 'anytime_td')), byWeek: Object.fromEntries([1,2,3].map(w => [w, compare(nonTD.filter(t => t.week === w))])), byMarket: Object.fromEntries([...new Set(cash.map(t => t.market))].map(m => [m, compare(cash.filter(t => t.market === m))])), sensitivity: { originalOnlyNonTD: compare(nonTD, 'original'), firstAvailableNonTD: compare(nonTD, 'first'), signChanges: nonTD.filter(t => Math.sign(t.first.ev) !== Math.sign(t.latest.ev)).map(t => ({ name: t.name, week: t.week, firstEV: t.first.ev, latestEV: t.latest.ev, profit: t.profit })) }, records };
emit(output, 'ev-observation', 2026, 3, true);
