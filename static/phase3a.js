/* Phase 3A: a temporary parlay slip using exact legs already evaluated in PropLens. */
(() => {
  const $ = selector => document.querySelector(selector);
  const labels = { passing_yards: 'Passing yards', passing_tds: 'Passing TDs', passing_interceptions: 'Interceptions', rushing_yards: 'Rushing yards', receiving_yards: 'Receiving yards', receptions: 'Receptions', anytime_td: 'Anytime TD' };
  const modal = $('#parlay-modal'), list = $('#parlay-leg-list'), count = $('#parlay-leg-count'), oddsInput = $('#parlay-odds'), stakeInput = $('#parlay-stake'), boostInput = $('#parlay-boost'), actualReturnInput = $('#parlay-actual-return'), results = $('#parlay-results'), warning = $('#parlay-warning'), guide = $('#parlay-reading-guide'), clear = $('#btn-clear-parlay'), sensitivityToggle = $('#btn-toggle-parlay-sensitivity'), suggestions = $('#toast-container');
  const key = 'proplens.phase3a.parlay-slip';
  let legs = [], sensitivityOpen = false;
  const escapeHtml = value => String(value ?? '').replace(/[&<>'"]/g, character => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;' }[character]));
  const money = value => `$${Number(value || 0).toFixed(2)}`;
  const percent = value => `${(Number(value) * 100).toFixed(1)}%`;
  const toast = (message, error = false) => { const item = document.createElement('div'); item.className = `toast${error ? ' error' : ''}`; item.textContent = message; suggestions.append(item); setTimeout(() => item.remove(), 4200); };
  const save = () => { try { sessionStorage.setItem(key, JSON.stringify(legs)); } catch { /* A temporary slip still works for this page. */ } };
  const load = () => { try { const saved = JSON.parse(sessionStorage.getItem(key) || '[]'); legs = Array.isArray(saved) ? saved.filter(leg => leg && Number(leg.probability) > 0 && Number(leg.probability) < 1) : []; } catch { legs = []; } };
  const gameKey = leg => [leg.team || '', leg.opponent || ''].filter(Boolean).sort().join('|');
  const gameLabel = leg => [leg.team, leg.opponent].filter(Boolean).join(' vs ');
  const duplicateKey = leg => `${leg.player_name}|${leg.market}|${leg.side_label}|${leg.line}|${leg.decimal_odds}`;
  const sameGame = () => { const games = legs.map(gameKey).filter(Boolean); return new Set(games).size < games.length; };
  const metric = (label, value, help, tone = '') => `<div class="parlay-metric ${tone}"><span>${label}<button type="button" class="parlay-info" aria-label="Explain ${label}">i<span class="parlay-tooltip" role="tooltip">${help}</span></button></span><strong>${value}</strong></div>`;
  function render() {
    count.textContent = legs.length;
    clear.hidden = !legs.length;
    sensitivityToggle.hidden = !legs.length;
    sensitivityToggle.classList.toggle('active', sensitivityOpen);
    sensitivityToggle.setAttribute('aria-pressed', String(sensitivityOpen));
    sensitivityToggle.textContent = sensitivityOpen ? 'Hide personal sensitivity' : 'Personal sensitivity';
    list.innerHTML = legs.length ? legs.map((leg, index) => `<article class="parlay-leg ${sensitivityOpen ? 'sensitivity-open' : ''}"><div><strong>${escapeHtml(leg.player_name)} · ${escapeHtml(leg.side_label)} ${leg.line} · ${escapeHtml(labels[leg.market] || leg.market)}</strong><small>${escapeHtml(gameLabel(leg))} · Bet365 ${Number(leg.decimal_odds).toFixed(2)}</small>${sensitivityOpen ? `<label class="parlay-belief-label">Your probability <span>optional · model ${percent(leg.probability)}</span><input class="parlay-belief-input" data-belief-leg="${index}" inputmode="decimal" min="0.1" max="99.9" placeholder="e.g. 45" value="${leg.belief_probability === undefined ? '' : (Number(leg.belief_probability) * 100).toFixed(1)}"></label>` : ''}</div><span class="parlay-leg-prob">${percent(leg.probability)} model</span><button type="button" class="parlay-remove" data-remove-parlay-leg="${index}">Remove</button></article>`).join('') : '<p class="field-help">Evaluate a prop, then choose Add to parlay. Your temporary slip can hold up to 10 legs.</p>';
    const correlated = sameGame();
    warning.hidden = !legs.length;
    warning.innerHTML = correlated ? '<strong>Same-game legs detected — no true EV verdict yet.</strong> Bet365 can price the relationship between these legs into its SGP odds. The figures below deliberately assume the legs are unrelated, so do not treat a positive or negative result as correlation-adjusted value.' : '<strong>Cross-game baseline.</strong> These legs are treated as independent. The result is still a model estimate, not a guaranteed edge.';
    calculate();
  }
  function calculate() {
    window.proplensParlayDraft = null;
    const combinedOdds = Number(oddsInput.value), stake = stakeInput.value.trim() === '' ? null : Number(stakeInput.value), boostPercent = boostInput.value.trim() === '' ? 0 : Number(boostInput.value), actualReturn = actualReturnInput.value.trim() === '' ? null : Number(actualReturnInput.value);
    if (legs.length < 2 || !Number.isFinite(combinedOdds) || combinedOdds <= 1) { results.innerHTML = '<p class="field-help">Add at least two evaluated legs and enter the actual Bet365 combined price to calculate the baseline.</p>'; guide.hidden = true; return; }
    if (!Number.isFinite(boostPercent) || boostPercent < 0) { results.innerHTML = '<p class="field-help">Enter a profit boost of 0% or more.</p>'; guide.hidden = true; return; }
    if (actualReturn !== null && (!Number.isFinite(actualReturn) || actualReturn < 0 || stake === null || !Number.isFinite(stake) || stake <= 0)) { results.innerHTML = '<p class="field-help">Enter a stake greater than $0 before using an actual boosted return.</p>'; guide.hidden = true; return; }
    if (actualReturn !== null && actualReturn < stake) { results.innerHTML = '<p class="field-help">Actual boosted return cannot be less than the stake.</p>'; guide.hidden = true; return; }
    const probability = legs.reduce((total, leg) => total * Number(leg.probability), 1);
    const beliefProbability = legs.reduce((total, leg) => total * (Number.isFinite(Number(leg.belief_probability)) && Number(leg.belief_probability) > 0 && Number(leg.belief_probability) < 1 ? Number(leg.belief_probability) : Number(leg.probability)), 1);
    const boostRate = boostPercent / 100;
    const effectiveOdds = actualReturn !== null ? actualReturn / stake : 1 + ((combinedOdds - 1) * (1 + boostRate));
    const fairOdds = 1 / probability, breakEven = 1 / effectiveOdds, ev = probability * effectiveOdds - 1;
    const boostLabel = actualReturn !== null ? 'Exact return override' : boostPercent ? `+${boostPercent.toFixed(1)}% profit boost` : 'No boost';
    const totalReturn = stake !== null && Number.isFinite(stake) && stake >= 0 ? (actualReturn ?? stake * effectiveOdds) : null;
    const stakeDetails = totalReturn !== null ? `<div class="parlay-stake-details"><p>Win outcome: <strong>${money(totalReturn)} return</strong> <span>(${money(totalReturn - stake)} net profit)</span></p><p>Independent long-run estimated net result: <strong class="${ev >= 0 ? 'positive' : 'negative'}">${ev >= 0 ? '+' : ''}${money(stake * ev)}</strong></p></div>` : '';
    const beliefChanged = legs.some(leg => Number.isFinite(Number(leg.belief_probability)) && Number(leg.belief_probability) > 0 && Number(leg.belief_probability) < 1 && Number(leg.belief_probability) !== Number(leg.probability));
    const beliefFairOdds = 1 / beliefProbability, beliefEv = beliefProbability * effectiveOdds - 1;
    const sensitivity = sensitivityOpen ? `<section class="parlay-sensitivity-results"><div><strong>Personal sensitivity — not the model</strong><span>${beliefChanged ? 'Uses your entered probabilities where provided; all other legs remain at their model probability.' : 'No personal probabilities entered yet; this matches the model baseline.'}</span></div><div class="parlay-sensitivity-metrics"><p>Your parlay chance <strong>${percent(beliefProbability)}</strong></p><p>Your fair odds <strong>${beliefFairOdds.toFixed(2)}</strong></p><p>Your baseline EV <strong class="${beliefEv >= 0 ? 'positive' : 'negative'}">${beliefEv >= 0 ? '+' : ''}${(beliefEv * 100).toFixed(1)}%</strong></p></div></section>` : '';
    window.proplensParlayDraft = { legs, original_decimal_odds: combinedOdds, effective_decimal_odds: effectiveOdds, stake, profit_boost_pct: boostPercent, actual_total_return: actualReturn, independent_model_probability: probability, personal_sensitivity_probability: sensitivityOpen ? beliefProbability : null };
    results.innerHTML = `<div class="parlay-metrics">${metric('Independent win chance', percent(probability), 'Multiply each leg\'s model win probability. This is only a baseline when the legs are from the same game.')}${metric('Independent fair odds', fairOdds.toFixed(2), 'The decimal odds that would break even in the long run if the independent win chance were correct. It equals 1 divided by that chance.')}${metric('Original Bet365 odds', combinedOdds.toFixed(2), 'The unboosted combined decimal odds from Bet365. The boost is applied separately to the profit portion.')}${metric('Boost treatment', boostLabel, 'A standard profit boost increases only profit, not the stake. An exact total-return entry overrides the percentage because unusual offers can use different rules.')}${metric('Effective boosted odds', effectiveOdds.toFixed(2), 'The decimal odds equivalent of the entered profit boost or exact total return. Break-even chance and the independence baseline use this effective price.')}${metric('Boosted break-even chance', percent(breakEven), 'The win chance required to break even at the effective boosted odds. It equals 1 divided by those odds.')}${metric('Independent-baseline EV', `${ev >= 0 ? '+' : ''}${(ev * 100).toFixed(1)}%`, 'The estimated long-run return per dollar staked using the effective boosted odds. For same-game parlays, this is not correlation-adjusted EV.', ev >= 0 ? 'positive' : 'negative')}</div>${stakeDetails}${sensitivity}<button type="button" class="parlay-save-button" id="btn-save-parlay">Track this parlay</button>`;
    guide.hidden = false;
    const boostNote = actualReturn !== null ? 'The exact boosted return you entered overrides the percentage field.' : boostPercent ? `The calculator applies the ${boostPercent.toFixed(1)}% boost to profit only.` : 'No boost is applied.';
    guide.innerHTML = sameGame() ? `<strong>How to read this:</strong> ${boostNote} The values below show what the parlay would look like if its legs were unrelated; they do not measure the true likelihood of this same-game parlay.` : `<strong>How to read this:</strong> ${boostNote} The calculator multiplies the model probability for each leg, so model error still matters.`;
  }
  function addEvaluation(data) {
    const { prop, model } = data || {};
    const probability = Number(model?.win_probability), odds = Number(prop?.bet365_decimal);
    if (!prop || !Number.isFinite(probability) || probability <= 0 || probability >= 1 || !Number.isFinite(odds) || odds <= 1) return toast('Evaluate a complete prop before adding it to a parlay.', true);
    const leg = { player_name: prop.player_name, team: prop.team, opponent: prop.opponent, market: prop.market, side_label: prop.side_label, line: prop.line, decimal_odds: odds, probability, result_identity: data.result_identity || null };
    if (legs.some(existing => duplicateKey(existing) === duplicateKey(leg))) return toast('That exact leg is already in your parlay slip.', true);
    if (legs.length >= 10) return toast('A temporary parlay slip can hold up to 10 legs.', true);
    legs.push(leg); save(); render(); toast(`${leg.player_name} added to your parlay slip.`);
  }
  $('#btn-open-parlay').addEventListener('click', () => { modal.hidden = false; render(); });
  document.addEventListener('click', event => { const button = event.target.closest('#btn-add-to-parlay'); if (button) addEvaluation(window.proplensLatestEvaluation); const remove = event.target.closest('[data-remove-parlay-leg]'); if (remove) { legs.splice(Number(remove.dataset.removeParlayLeg), 1); save(); render(); } });
  sensitivityToggle.addEventListener('click', () => { sensitivityOpen = !sensitivityOpen; render(); });
  list.addEventListener('input', event => { const input = event.target.closest('[data-belief-leg]'); if (!input) return; const value = input.value.trim() === '' ? undefined : Number(input.value) / 100; const index = Number(input.dataset.beliefLeg); if (!Number.isFinite(value) && value !== undefined) return; if (value !== undefined && (value <= 0 || value >= 1)) return toast('Enter a personal probability between 0.1% and 99.9%.', true); legs[index].belief_probability = value; save(); calculate(); });
  clear.addEventListener('click', () => { if (!window.confirm('Clear every leg from this temporary parlay slip?')) return; legs = []; save(); render(); });
  [oddsInput, stakeInput, boostInput, actualReturnInput].forEach(input => input.addEventListener('input', calculate));
  load(); render();
})();
