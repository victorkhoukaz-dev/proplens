/* Phase 4H: later projection snapshots for guided manual-parlay player props. */
(() => {
  const $ = selector => document.querySelector(selector);
  const escapeHtml = value => String(value ?? '').replace(/[&<>'"]/g, character => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;' }[character]));
  const marketLabel = market => ({ passing_yards: 'Passing yards', passing_tds: 'Passing TDs', passing_interceptions: 'Passing interceptions', rushing_yards: 'Rushing yards', rushing_attempts: 'Rushing attempts', rushing_receiving_yards: 'Rushing + receiving yards', receiving_yards: 'Receiving yards', receptions: 'Receptions', anytime_td: 'Anytime TD' }[market] || String(market || '').replaceAll('_', ' '));
  const toast = (message, error = false) => { const item = document.createElement('div'); item.className = `toast${error ? ' error' : ''}`; item.textContent = message; $('#toast-container').append(item); setTimeout(() => item.remove(), 4200); };
  const api = async (url, options) => { const response = await fetch(url, options); const data = await response.json().catch(() => ({})); if (!response.ok) throw new Error(data.detail || 'Something went wrong.'); return data; };

  document.body.insertAdjacentHTML('beforeend', `
    <div class="modal-backdrop" id="parlay-later-evaluation-modal" hidden>
      <section class="modal-card parlay-later-evaluation-card" role="dialog" aria-modal="true" aria-labelledby="parlay-later-evaluation-title">
        <button class="modal-close" data-close-parlay-later-evaluation aria-label="Close">×</button>
        <p class="eyebrow">PHASE 4H · LATER EVALUATION</p>
        <h2 id="parlay-later-evaluation-title">Evaluate manual parlay legs</h2>
        <p id="parlay-later-evaluation-summary"></p>
        <div id="parlay-later-evaluation-list" class="parlay-later-evaluation-list"></div>
        <p class="later-evaluation-note">Each selected leg receives a separate timestamped model snapshot. The parlay remains Manual. A cross-game baseline appears only after every leg has a compatible evaluation.</p>
        <button type="button" class="secondary-button" id="btn-save-parlay-later-evaluations">Save selected leg evaluations</button>
      </section>
    </div>`);

  const modal = $('#parlay-later-evaluation-modal');
  let targetParlay = null;
  let matchingPlayers = new Map();

  function compatible(leg) {
    return leg.entry_mode === 'structured' && leg.category === 'player_prop' && ['passing_yards', 'passing_tds', 'passing_interceptions', 'rushing_yards', 'rushing_attempts', 'rushing_receiving_yards', 'receiving_yards', 'receptions', 'anytime_td'].includes(leg.market);
  }

  async function candidatesFor(leg) {
    const data = await api(`/api/evaluator/players?q=${encodeURIComponent(leg.player_name || '')}&limit=20`);
    return (data.players || []).filter(player => (player.markets || []).includes(leg.market));
  }

  async function open(parlay) {
    targetParlay = parlay;
    matchingPlayers = new Map();
    $('#parlay-later-evaluation-summary').textContent = `${parlay.description || `${parlay.legs.length}-leg manual parlay`} · add each leg's exact Bet365 decimal odds before saving.`;
    const eligible = parlay.legs.map((leg, index) => ({ leg, index })).filter(({ leg }) => compatible(leg));
    const skipped = parlay.legs.length - eligible.length;
    if (!eligible.length) return toast('This parlay has no guided player-prop legs that the evaluator supports yet.', true);
    $('#parlay-later-evaluation-list').innerHTML = eligible.map(({ leg, index }) => `<article class="parlay-later-evaluation-row" data-parlay-leg-index="${index}"><label><input type="checkbox" checked> Evaluate</label><strong>${escapeHtml(leg.description)}</strong><small>${escapeHtml(marketLabel(leg.market))}${leg.market === 'anytime_td' ? ' · evaluated as Yes 0.5' : ''}</small><label>Imported player<select disabled><option>Loading matches…</option></select></label><label>Exact decimal odds<input inputmode="decimal" min="1.01" value="${Number.isFinite(Number(leg.decimal_odds)) ? Number(leg.decimal_odds).toFixed(2) : ''}" placeholder="e.g. 1.90"></label><p class="field-help"></p></article>`).join('') + (skipped ? `<p class="field-help">${skipped} leg${skipped === 1 ? '' : 's'} remain tracking-only because they are free text, non-player markets, or unsupported props.</p>` : '');
    modal.hidden = false;
    await Promise.all(eligible.map(async ({ leg, index }) => {
      const row = modal.querySelector(`[data-parlay-leg-index="${index}"]`);
      try {
        const players = await candidatesFor(leg);
        matchingPlayers.set(index, players);
        const select = row.querySelector('select');
        select.disabled = !players.length;
        select.innerHTML = players.length ? players.map((player, playerIndex) => `<option value="${playerIndex}">${escapeHtml(player.player_name)} · ${escapeHtml(player.position)} · ${escapeHtml(player.team)} vs ${escapeHtml(player.opponent || '—')}</option>`).join('') : '<option>No compatible loaded projection</option>';
        row.querySelector('.field-help').textContent = players.length ? 'Confirm the player and enter the exact price shown by Bet365.' : 'No compatible projection is loaded for this player and market.';
      } catch (error) { row.querySelector('.field-help').textContent = error.message; }
    }));
  }

  document.addEventListener('click', event => {
    const close = event.target.closest('[data-close-parlay-later-evaluation]');
    if (close) modal.hidden = true;
    const button = event.target.closest('[data-later-evaluate-parlay]');
    if (!button) return;
    const parlay = (window.proplensTrackedParlays || []).find(item => item.id === button.dataset.laterEvaluateParlay);
    if (parlay) open(parlay).catch(error => toast(error.message, true));
  });
  modal.addEventListener('click', event => { if (event.target === modal) modal.hidden = true; });
  $('#btn-save-parlay-later-evaluations').addEventListener('click', async event => {
    if (!targetParlay) return;
    const selected = [...modal.querySelectorAll('.parlay-later-evaluation-row')].filter(row => row.querySelector('input[type="checkbox"]').checked);
    if (!selected.length) return toast('Select at least one compatible leg.', true);
    const legs = [];
    for (const row of selected) {
      const index = Number(row.dataset.parlayLegIndex), players = matchingPlayers.get(index) || [], player = players[Number(row.querySelector('select').value)], odds = Number(row.querySelector('input[inputmode="decimal"]').value);
      if (!player) return toast('Choose a loaded projection match for every selected leg.', true);
      if (!Number.isFinite(odds) || odds <= 1) return toast('Enter decimal odds above 1.00 for every selected leg.', true);
      legs.push({ leg_index: index, player_name: player.player_name, decimal_odds: odds });
    }
    const button = event.currentTarget; button.disabled = true;
    try {
      const result = await api(`/api/tracker/parlays/${targetParlay.id}/later-evaluations`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ legs }) });
      modal.hidden = true;
      await window.proplensRefreshTracker?.();
      toast(result.baseline ? 'Leg evaluations saved with a cross-game model baseline.' : 'Selected leg evaluations saved.');
    } catch (error) { toast(error.message, true); } finally { button.disabled = false; }
  });
})();
