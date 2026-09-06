/* Phase 3A: a temporary parlay slip using exact legs already evaluated in PropLens. */
(() => {
  const $ = selector => document.querySelector(selector);
  const labels = { passing_yards: 'Passing yards', passing_tds: 'Passing TDs', passing_interceptions: 'Interceptions', rushing_yards: 'Rushing yards', receiving_yards: 'Receiving yards', receptions: 'Receptions', anytime_td: 'Anytime TD' };
  const modal = $('#parlay-modal'), list = $('#parlay-leg-list'), count = $('#parlay-leg-count'), oddsInput = $('#parlay-odds'), stakeInput = $('#parlay-stake'), results = $('#parlay-results'), warning = $('#parlay-warning'), clear = $('#btn-clear-parlay'), suggestions = $('#toast-container');
  const key = 'proplens.phase3a.parlay-slip';
  let legs = [];
  const escapeHtml = value => String(value ?? '').replace(/[&<>'"]/g, character => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;' }[character]));
  const money = value => `$${Number(value || 0).toFixed(2)}`;
  const percent = value => `${(Number(value) * 100).toFixed(1)}%`;
  const toast = (message, error = false) => { const item = document.createElement('div'); item.className = `toast${error ? ' error' : ''}`; item.textContent = message; suggestions.append(item); setTimeout(() => item.remove(), 4200); };
  const save = () => { try { sessionStorage.setItem(key, JSON.stringify(legs)); } catch { /* A temporary slip still works for this page. */ } };
  const load = () => { try { const saved = JSON.parse(sessionStorage.getItem(key) || '[]'); legs = Array.isArray(saved) ? saved.filter(leg => leg && Number(leg.probability) > 0 && Number(leg.probability) < 1) : []; } catch { legs = []; } };
  const gameKey = leg => [leg.team || '', leg.opponent || ''].filter(Boolean).sort().join('|');
  const duplicateKey = leg => `${leg.player_name}|${leg.market}|${leg.side_label}|${leg.line}|${leg.decimal_odds}`;
  const sameGame = () => { const games = legs.map(gameKey).filter(Boolean); return new Set(games).size < games.length; };
  function render() {
    count.textContent = legs.length;
    clear.hidden = !legs.length;
    list.innerHTML = legs.length ? legs.map((leg, index) => `<article class="parlay-leg"><div><strong>${escapeHtml(leg.player_name)} · ${escapeHtml(leg.side_label)} ${leg.line} · ${escapeHtml(labels[leg.market] || leg.market)}</strong><small>${escapeHtml(leg.team || '')}${leg.opponent ? ` vs ${escapeHtml(leg.opponent)}` : ''} · Bet365 ${Number(leg.decimal_odds).toFixed(2)}</small></div><span class="parlay-leg-prob">${percent(leg.probability)} model</span><button type="button" class="parlay-remove" data-remove-parlay-leg="${index}">Remove</button></article>`).join('') : '<p class="field-help">Evaluate a prop, then choose Add to parlay. Your temporary slip can hold up to 10 legs.</p>';
    const correlated = sameGame();
    warning.hidden = !legs.length;
    warning.textContent = correlated ? 'Same-game legs detected. Bet365 may price their relationship into the SGP price. The figures below are an independence baseline only, not correlation-adjusted EV.' : 'Different-game legs are shown as an independence baseline. It still remains a model estimate, not a guaranteed edge.';
    calculate();
  }
  function calculate() {
    const combinedOdds = Number(oddsInput.value), stake = stakeInput.value.trim() === '' ? null : Number(stakeInput.value);
    if (legs.length < 2 || !Number.isFinite(combinedOdds) || combinedOdds <= 1) { results.innerHTML = '<p class="field-help">Add at least two evaluated legs and enter the actual Bet365 combined price to calculate the baseline.</p>'; return; }
    const probability = legs.reduce((total, leg) => total * Number(leg.probability), 1);
    const fairOdds = 1 / probability, breakEven = 1 / combinedOdds, ev = probability * combinedOdds - 1;
    const expected = stake !== null && Number.isFinite(stake) && stake >= 0 ? `<p class="parlay-expected">Expected result on ${money(stake)} stake: <strong class="${ev >= 0 ? 'positive' : 'negative'}">${ev >= 0 ? '+' : ''}${money(stake * ev)}</strong></p>` : '';
    results.innerHTML = `<div class="parlay-metrics"><div class="parlay-metric"><span>Independent win chance</span><strong>${percent(probability)}</strong></div><div class="parlay-metric"><span>Independent fair odds</span><strong>${fairOdds.toFixed(2)}</strong></div><div class="parlay-metric"><span>Bet365 break-even chance</span><strong>${percent(breakEven)}</strong></div><div class="parlay-metric ${ev >= 0 ? 'positive' : 'negative'}"><span>Independent-baseline EV</span><strong>${ev >= 0 ? '+' : ''}${(ev * 100).toFixed(1)}%</strong></div></div>${expected}`;
  }
  function addEvaluation(data) {
    const { prop, model } = data || {};
    const probability = Number(model?.win_probability), odds = Number(prop?.bet365_decimal);
    if (!prop || !Number.isFinite(probability) || probability <= 0 || probability >= 1 || !Number.isFinite(odds) || odds <= 1) return toast('Evaluate a complete prop before adding it to a parlay.', true);
    const leg = { player_name: prop.player_name, team: prop.team, opponent: prop.opponent, market: prop.market, side_label: prop.side_label, line: prop.line, decimal_odds: odds, probability };
    if (legs.some(existing => duplicateKey(existing) === duplicateKey(leg))) return toast('That exact leg is already in your parlay slip.', true);
    if (legs.length >= 10) return toast('A temporary parlay slip can hold up to 10 legs.', true);
    legs.push(leg); save(); render(); toast(`${leg.player_name} added to your parlay slip.`);
  }
  $('#btn-open-parlay').addEventListener('click', () => { modal.hidden = false; render(); });
  document.addEventListener('click', event => { const button = event.target.closest('#btn-add-to-parlay'); if (button) addEvaluation(window.proplensLatestEvaluation); const remove = event.target.closest('[data-remove-parlay-leg]'); if (remove) { legs.splice(Number(remove.dataset.removeParlayLeg), 1); save(); render(); } });
  clear.addEventListener('click', () => { if (!window.confirm('Clear every leg from this temporary parlay slip?')) return; legs = []; save(); render(); });
  [oddsInput, stakeInput].forEach(input => input.addEventListener('input', calculate));
  load(); render();
})();
