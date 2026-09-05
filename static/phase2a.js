/* Phase 2A: local straight-bet tracker with compact ledger controls. */
(() => {
  const $ = selector => document.querySelector(selector);
  const trackerModal = $('#tracker-modal'), saveModal = $('#save-bet-modal'), editModal = $('#edit-bet-modal'), cashoutModal = $('#cashout-modal');
  const trackerList = $('#tracker-list'), trackerSummary = $('#tracker-summary'), trackerIncludePending = $('#tracker-include-pending'), trackerSearch = $('#tracker-search'), trackerStatusFilter = $('#tracker-status-filter'), trackerTypeFilter = $('#tracker-type-filter'), trackerSort = $('#tracker-sort'), trackerVisibleCount = $('#tracker-visible-count'), betType = $('#tracker-bet-type'), stake = $('#tracker-stake'), bonusHelp = $('#tracker-bonus-help');
  let selectedBet = null, latestTrackerData = null;
  const escapeHtml = value => String(value ?? '').replace(/[&<>'"]/g, char => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;' }[char]));
  const money = value => `$${Number(value || 0).toFixed(2)}`;
  const percent = value => value === null || value === undefined ? '—' : `${Number(value).toFixed(1)}%`;
  const toast = (message, error = false) => { const item = document.createElement('div'); item.className = `toast${error ? ' error' : ''}`; item.textContent = message; $('#toast-container').append(item); setTimeout(() => item.remove(), 4200); };
  const marketLabel = market => ({ rushing_yards: 'Rushing yards', receiving_yards: 'Receiving yards', receptions: 'Receptions', anytime_td: 'Anytime TD' }[market] || String(market || '').replaceAll('_', ' '));
  const statusLabel = bet => bet.status === 'cashed_out' ? `Cashed out · ${money(bet.settlement_amount)} received` : bet.status === 'cancelled' ? 'Cancelled before start' : bet.status[0].toUpperCase() + bet.status.slice(1);
  async function api(url, options) { const response = await fetch(url, options); const data = await response.json().catch(() => ({})); if (!response.ok) throw new Error(data.detail || 'Something went wrong.'); return data; }

  function filteredBets(bets) {
    const search = trackerSearch.value.trim().toLowerCase(), status = trackerStatusFilter.value, type = trackerTypeFilter.value;
    return bets.filter(bet => {
      const matchesSearch = !search || `${bet.player_name} ${bet.market} ${bet.team || ''} ${bet.opponent || ''}`.toLowerCase().includes(search);
      const matchesStatus = status === 'all' || (status === 'settled' ? bet.status !== 'pending' : bet.status === status);
      return matchesSearch && matchesStatus && (type === 'all' || bet.bet_type === type);
    }).sort((a, b) => {
      if (trackerSort.value === 'pending_first' && (a.status === 'pending') !== (b.status === 'pending')) return a.status === 'pending' ? -1 : 1;
      if (trackerSort.value === 'player') return a.player_name.localeCompare(b.player_name);
      return (trackerSort.value === 'oldest' ? 1 : -1) * String(a.created_at).localeCompare(String(b.created_at));
    });
  }
  function moreActions(bet) {
    const pendingActions = bet.status === 'pending' ? `<button data-settle="push" data-bet-id="${bet.id}">Push</button><button data-cancel="${bet.id}">Cancel before start</button>` : '';
    return `<details class="row-more"><summary aria-label="More actions for ${escapeHtml(bet.player_name)}">More</summary><div class="row-more-menu"><button data-edit="${bet.id}">Edit</button>${pendingActions}<button class="danger-action" data-delete="${bet.id}">Delete</button></div></details>`;
  }
  function rowMarkup(bet) {
    const matchup = bet.team ? `${escapeHtml(bet.team)}${bet.opponent ? ` vs ${escapeHtml(bet.opponent)}` : ''} · ` : '';
    const profit = Number(bet.profit || 0), settled = bet.status !== 'pending';
    const actions = bet.status === 'pending' ? `<button class="settle-win" data-settle="won" data-bet-id="${bet.id}">Won</button><button data-settle="lost" data-bet-id="${bet.id}">Lost</button><button data-cashout="${bet.id}">Cash out</button>${moreActions(bet)}` : moreActions(bet);
    return `<article class="tracked-bet ${bet.status === 'pending' ? 'is-pending' : 'is-settled'}"><div class="bet-identity"><strong>${escapeHtml(bet.player_name)}</strong><span class="bet-prop">${escapeHtml(bet.side_label)} ${bet.line} · ${marketLabel(bet.market)}</span><small>${matchup}${Number(bet.decimal_odds).toFixed(2)} · ${bet.bet_type === 'bonus' ? 'Bonus' : 'Cash'} · ${money(bet.stake)}</small></div><div class="bet-status ${bet.status}"><span>${statusLabel(bet)}</span>${settled ? `<strong class="${profit >= 0 ? 'positive' : 'negative'}">${profit >= 0 ? '+' : ''}${money(profit)}</strong>` : ''}</div><div class="settle-actions">${actions}</div></article>`;
  }
  function render(data) {
    latestTrackerData = data; window.proplensTrackedBets = data.bets;
    const s = data.summary;
    if (!Object.hasOwn(s, 'cash_wagered') || !Object.hasOwn(s, 'total_roi_on_cash_risk_pct')) { trackerSummary.innerHTML = '<p class="field-help">The tracker display has been updated, but its calculation service is still running an older version. Close the existing “NFL Betting App” window, then run Start Betting App.bat again.</p>'; return; }
    trackerSummary.innerHTML = `<div><span>Pending</span><strong>${s.pending}</strong></div><div><span>Cash-bet P/L</span><strong class="${s.cash_profit >= 0 ? 'positive' : 'negative'}">${s.cash_profit >= 0 ? '+' : ''}${money(s.cash_profit)}</strong></div><div><span>Bonus-bet cash profit</span><strong class="${s.bonus_profit >= 0 ? 'positive' : 'negative'}">${s.bonus_profit >= 0 ? '+' : ''}${money(s.bonus_profit)}</strong></div><div><span>Total net profit</span><strong class="${s.total_profit >= 0 ? 'positive' : 'negative'}">${s.total_profit >= 0 ? '+' : ''}${money(s.total_profit)}</strong></div><div><span>Cash-bet ROI</span><strong>${percent(s.cash_roi_pct)}</strong></div><div><span>Total ROI on cash risk</span><strong>${percent(s.total_roi_on_cash_risk_pct)}</strong></div><div><span>Cash wagered</span><strong>${money(s.cash_wagered)}</strong></div><div><span>Bonus value used</span><strong>${money(s.bonus_stake_used)}</strong></div>`;
    const visibleBets = filteredBets(data.bets); trackerVisibleCount.textContent = `Showing ${visibleBets.length} of ${data.bets.length}`;
    trackerList.innerHTML = visibleBets.length ? visibleBets.map(rowMarkup).join('') : '<p class="field-help tracker-empty">No bets match these filters.</p>';
  }
  async function loadTracker() { render(await api(`/api/tracker/bets?include_pending=${trackerIncludePending.checked}`)); }
  const findBet = id => (window.proplensTrackedBets || []).find(bet => bet.id === id);
  const refreshVisibleTracker = () => { if (latestTrackerData) render(latestTrackerData); };
  $('#btn-open-tracker').addEventListener('click', async () => { trackerModal.hidden = false; try { await loadTracker(); } catch (error) { toast(error.message, true); } });
  trackerIncludePending.addEventListener('change', () => loadTracker().catch(error => toast(error.message, true)));
  [trackerSearch, trackerStatusFilter, trackerTypeFilter, trackerSort].forEach(control => control.addEventListener('input', refreshVisibleTracker));
  document.addEventListener('click', event => { const button = event.target.closest('#btn-save-evaluation'); if (!button) return; const evaluation = window.proplensLatestEvaluation; if (!evaluation) return toast('Evaluate this prop before saving it.', true); $('#save-bet-summary').textContent = `${evaluation.prop.player_name} ${evaluation.prop.side_label} ${evaluation.prop.line} at ${Number(evaluation.prop.bet365_decimal).toFixed(2)}.`; stake.value = evaluation.value.entered_stake ?? ''; betType.value = 'cash'; bonusHelp.hidden = true; saveModal.hidden = false; });
  betType.addEventListener('change', () => { bonusHelp.hidden = betType.value !== 'bonus'; });
  $('#btn-save-tracked-bet').addEventListener('click', async event => { const evaluation = window.proplensLatestEvaluation, amount = Number(stake.value); if (!evaluation || !amount || amount <= 0) return toast('Enter the actual stake or bonus-bet value.', true); const button = event.currentTarget; button.disabled = true; try { const { prop, projection, model, value } = evaluation; await api('/api/tracker/bets', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ player_name: prop.player_name, team: prop.team, opponent: prop.opponent, market: prop.market, side_label: prop.side_label, line: prop.line, decimal_odds: prop.bet365_decimal, stake: amount, bet_type: betType.value, projection_mean: projection.mean, model_win_probability: model.win_probability, model_fair_decimal: model.fair_decimal, expected_value_pct: value.expected_value_pct }) }); saveModal.hidden = true; toast('Saved as a pending bet.'); } catch (error) { toast(error.message, true); } finally { button.disabled = false; } });
  trackerList.addEventListener('click', async event => {
    const button = event.target.closest('button'); if (!button) return;
    if (button.dataset.edit) { selectedBet = findBet(button.dataset.edit); if (!selectedBet) return; $('#edit-bet-summary').textContent = `${selectedBet.player_name} ${selectedBet.side_label} ${selectedBet.line}`; $('#edit-bet-type').value = selectedBet.bet_type; $('#edit-bet-stake').value = selectedBet.stake; $('#edit-bet-line').value = selectedBet.line; $('#edit-bet-odds').value = selectedBet.decimal_odds; $('#edit-bet-status').value = selectedBet.status; $('#edit-settlement-amount').value = selectedBet.settlement_amount ?? ''; editModal.hidden = false; return; }
    if (button.dataset.cashout) { selectedBet = findBet(button.dataset.cashout); if (!selectedBet) return; $('#cashout-summary').textContent = `${selectedBet.player_name} ${selectedBet.side_label} ${selectedBet.line} · stake ${money(selectedBet.stake)}`; $('#cashout-amount').value = ''; cashoutModal.hidden = false; return; }
    try { if (button.dataset.delete) { if (!window.confirm('Delete this tracked bet permanently? This cannot be undone.')) return; await api(`/api/tracker/bets/${button.dataset.delete}`, { method: 'DELETE' }); toast('Tracked bet deleted.'); } else if (button.dataset.cancel) { if (!window.confirm('Cancel this pending bet? It will remain in history with $0.00 profit.')) return; await api(`/api/tracker/bets/${button.dataset.cancel}/settle`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ status: 'cancelled' }) }); } else if (button.dataset.settle) { await api(`/api/tracker/bets/${button.dataset.betId}/settle`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ status: button.dataset.settle }) }); } await loadTracker(); } catch (error) { toast(error.message, true); }
  });
  $('#btn-update-tracked-bet').addEventListener('click', async event => { if (!selectedBet) return; const status = $('#edit-bet-status').value, settlementText = $('#edit-settlement-amount').value.trim(); const body = { bet_type: $('#edit-bet-type').value, stake: Number($('#edit-bet-stake').value), line: Number($('#edit-bet-line').value), decimal_odds: Number($('#edit-bet-odds').value), status, settlement_amount: settlementText ? Number(settlementText) : null }; if (status === 'cashed_out' && !settlementText) return toast('Enter the actual cash-out amount.', true); const button = event.currentTarget; button.disabled = true; try { await api(`/api/tracker/bets/${selectedBet.id}`, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }); editModal.hidden = true; await loadTracker(); toast('Tracked bet corrected.'); } catch (error) { toast(error.message, true); } finally { button.disabled = false; } });
  $('#btn-confirm-cashout').addEventListener('click', async event => { if (!selectedBet) return; const amount = Number($('#cashout-amount').value); if (!Number.isFinite(amount) || amount < 0) return toast('Enter the actual cash-out amount.', true); const button = event.currentTarget; button.disabled = true; try { await api(`/api/tracker/bets/${selectedBet.id}/settle`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ status: 'cashed_out', settlement_amount: amount }) }); cashoutModal.hidden = true; await loadTracker(); toast('Cash-out recorded.'); } catch (error) { toast(error.message, true); } finally { button.disabled = false; } });
})();
