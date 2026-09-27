/* Optional batch entry for pending, tracking-only Anytime TD straight bets. */
(() => {
  const $ = selector => document.querySelector(selector);
  const escapeHtml = value => String(value ?? '').replace(/[&<>'"]/g, char => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;' }[char]));
  const button = document.createElement('button');
  button.type = 'button';
  button.id = 'btn-anytime-td-batch';
  button.className = 'tracker-manual-entry';
  button.textContent = 'Batch Anytime TD';
  $('#btn-manual-bet').insertAdjacentElement('afterend', button);

  document.body.insertAdjacentHTML('beforeend', `
    <div class="modal-backdrop" id="anytime-td-batch-modal" hidden>
      <section class="modal-card anytime-td-batch-card" role="dialog" aria-modal="true" aria-labelledby="anytime-td-batch-title">
        <button type="button" class="modal-close" id="anytime-td-batch-close" aria-label="Close">×</button>
        <p class="eyebrow">BATCH TRACKING · ANYTIME TD STRAIGHTS</p>
        <h2 id="anytime-td-batch-title">Track several Anytime TD bets</h2>
        <p class="field-help">Tracking only: Yes · 0.5 is filled for each bet. No projection or EV is created. Use a separate batch when bet type, decision source, or analyst differs.</p>
        <div id="anytime-td-batch-edit">
          <div class="anytime-td-batch-shared">
            <label>Season<input id="atd-batch-season" type="number" min="2020" max="2100" class="number-input" value="2026"></label>
            <label>NFL week<input id="atd-batch-week" type="number" min="1" max="25" class="number-input" placeholder="Required"></label>
            <label>Default stake ($)<input id="atd-batch-stake" type="number" min="0.01" step="0.01" class="number-input" value="5"></label>
            <label>Bet type<select id="atd-batch-type"><option value="cash">Cash</option><option value="bonus">Bonus</option></select></label>
            <label>Decision source<select id="atd-batch-source"><option value="">No note</option><option value="analyst">Analyst recommendation</option><option value="model">Model only</option><option value="own_analysis">My own analysis</option><option value="hedge">Hedge</option><option value="other">Other</option></select></label>
            <label id="atd-batch-analyst-label" hidden>Analyst<input id="atd-batch-analyst" class="number-input" list="analyst-options" placeholder="Choose or type a name"></label>
            <label class="atd-batch-note">Note <span>optional</span><input id="atd-batch-note" class="number-input" placeholder="Shared reminder for this batch"></label>
          </div>
          <p class="atd-batch-tip">Enter the exact player and Bet365 price. Team and opponent can fill from a unique active projection; check them before saving. A directory match may fill only the team.</p>
          <datalist id="atd-batch-player-options"></datalist>
          <div class="atd-batch-rows" id="atd-batch-rows"></div>
          <div class="atd-batch-actions"><button type="button" id="atd-batch-add-one">+ Add row</button><button type="button" id="atd-batch-add-ten">+ Add 10 rows</button><button type="button" class="secondary-button" id="atd-batch-review">Review bets →</button></div>
        </div>
        <div id="anytime-td-batch-review" hidden>
          <p id="atd-batch-review-summary" class="atd-batch-review-summary"></p>
          <div id="atd-batch-review-list" class="atd-batch-review-list"></div>
          <p id="atd-batch-review-warning" class="atd-batch-review-warning" hidden></p>
          <div class="atd-batch-actions"><button type="button" id="atd-batch-edit-again">← Edit batch</button><button type="button" class="secondary-button" id="atd-batch-save">Save reviewed bets</button></div>
        </div>
      </section>
    </div>`);

  const modal = $('#anytime-td-batch-modal');
  const rows = $('#atd-batch-rows');
  const editPanel = $('#anytime-td-batch-edit');
  const reviewPanel = $('#anytime-td-batch-review');
  let reviewedBets = null;
  let batchId = null;
  const lookupCache = new Map();
  let searchTimer = null;
  let searchSequence = 0;

  const toast = (message, error = false) => {
    const item = document.createElement('div');
    item.className = `toast${error ? ' error' : ''}`;
    item.textContent = message;
    $('#toast-container').append(item);
    setTimeout(() => item.remove(), 4200);
  };
  async function api(url, options) {
    const response = await fetch(url, options);
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      if (response.status === 404 && url.includes('anytime-td-batch')) throw new Error('Restart PropLens to activate batch saving. Your draft is still here.');
      const detail = Array.isArray(data.detail) ? data.detail.map(item => item.msg).join(' ') : data.detail;
      throw new Error(detail || 'Something went wrong.');
    }
    return data;
  }
  function addRows(count) {
    if (rows.children.length + count > 50) return toast('A batch can contain at most 50 rows.', true);
    for (let index = 0; index < count; index++) {
      const row = document.createElement('div');
      row.className = 'atd-batch-row';
      row.innerHTML = `<span class="atd-row-number"></span><label>Player<input data-field="player" class="number-input" list="atd-batch-player-options" placeholder="Exact player name" autocomplete="off"></label><label>Team<input data-field="team" class="number-input" placeholder="e.g. PHI" maxlength="4"></label><label>Opponent<input data-field="opponent" class="number-input" placeholder="e.g. DAL" maxlength="4"></label><label>Decimal odds<input data-field="odds" class="number-input" type="number" min="1.01" step="0.01" placeholder="e.g. 2.15"></label><label>Stake override<input data-field="stake" class="number-input" type="number" min="0.01" step="0.01" placeholder="Default"></label><button type="button" data-remove-row aria-label="Remove row">×</button>`;
      rows.append(row);
    }
    renumber();
  }
  function renumber() { [...rows.children].forEach((row, index) => { row.querySelector('.atd-row-number').textContent = String(index + 1); }); }
  const rowValue = (row, field) => row.querySelector(`[data-field="${field}"]`).value.trim();
  const usedRow = row => ['player', 'team', 'opponent', 'odds', 'stake'].some(field => rowValue(row, field));
  const projectionMatchesWeek = data => Number(data.projection_context?.season) === Number($('#atd-batch-season').value) && Number(data.projection_context?.week) === Number($('#atd-batch-week').value);

  async function lookupPlayer(name) {
    const normalized = name.toLocaleLowerCase();
    const key = `${$('#atd-batch-season').value}|${$('#atd-batch-week').value}|${normalized}`;
    if (!lookupCache.has(key)) {
      lookupCache.set(key, (async () => {
        const projections = await api(`/api/evaluator/players?q=${encodeURIComponent(name)}&limit=30`);
        const exact = projectionMatchesWeek(projections) ? (projections.players || []).filter(player => String(player.player_name || '').toLocaleLowerCase() === normalized) : [];
        const unique = new Map(exact.map(player => [`${player.team}|${player.opponent}`, player]));
        if (unique.size === 1) return [...unique.values()][0];
        if (unique.size > 1) return null;
        const directory = await api(`/api/player-directory/search?q=${encodeURIComponent(name)}&limit=50`);
        const directoryExact = (directory.players || []).filter(player => String(player.player_name || '').toLocaleLowerCase() === normalized);
        return new Map(directoryExact.map(player => [player.team, player])).size === 1 ? directoryExact[0] : null;
      })().catch(() => null));
    }
    return lookupCache.get(key);
  }
  async function resolveRow(row) {
    const name = rowValue(row, 'player');
    if (!name || (rowValue(row, 'team') && rowValue(row, 'opponent'))) return;
    const match = await lookupPlayer(name);
    if (!match || rowValue(row, 'player').toLocaleLowerCase() !== name.toLocaleLowerCase()) return;
    if (!rowValue(row, 'team')) row.querySelector('[data-field="team"]').value = match.team || '';
    if (!rowValue(row, 'opponent')) row.querySelector('[data-field="opponent"]').value = match.opponent || '';
  }
  async function resolveRows(used) {
    for (let offset = 0; offset < used.length; offset += 4) await Promise.all(used.slice(offset, offset + 4).map(resolveRow));
  }
  function reviewBets(used) {
    const season = Number($('#atd-batch-season').value);
    const week = Number($('#atd-batch-week').value);
    const defaultStake = Number($('#atd-batch-stake').value);
    const source = $('#atd-batch-source').value;
    const analyst = $('#atd-batch-analyst').value.trim();
    const note = $('#atd-batch-note').value.trim();
    if (!Number.isInteger(season) || season < 2020 || season > 2100 || !Number.isInteger(week) || week < 1 || week > 25) throw new Error('Choose a valid season and NFL week.');
    if (!Number.isFinite(defaultStake) || defaultStake <= 0) throw new Error('Enter a positive default stake.');
    if (source === 'analyst' && !analyst) throw new Error('Choose or type the analyst for this batch.');
    if (note && !source) throw new Error('Choose a decision source so the shared note is saved.');
    return used.map(row => {
      const number = row.querySelector('.atd-row-number').textContent;
      const player = rowValue(row, 'player');
      const team = rowValue(row, 'team').toUpperCase();
      const opponent = rowValue(row, 'opponent').toUpperCase();
      const odds = Number(rowValue(row, 'odds'));
      const stake = rowValue(row, 'stake') ? Number(rowValue(row, 'stake')) : defaultStake;
      if (!player || !team || !opponent) throw new Error(`Row ${number}: enter the player, team, and opponent.`);
      if (team === opponent) throw new Error(`Row ${number}: team and opponent cannot be the same.`);
      if (!Number.isFinite(odds) || odds <= 1) throw new Error(`Row ${number}: enter decimal odds above 1.00.`);
      if (!Number.isFinite(stake) || stake <= 0) throw new Error(`Row ${number}: enter a positive stake.`);
      return { category: 'player_prop', description: player, player_name: player, position: null, team, opponent,
        market: 'anytime_td', side_label: 'Yes', line: 0.5, decimal_odds: odds, stake,
        bet_type: $('#atd-batch-type').value, season, week, status: 'pending', settlement_amount: null,
        decision_context: source ? { source, ...(analyst ? { analyst } : {}), ...(note ? { note } : {}) } : null };
    });
  }
  function showReview(bets) {
    reviewedBets = bets;
    batchId ||= crypto.randomUUID();
    const cash = bets.filter(bet => bet.bet_type === 'cash').reduce((sum, bet) => sum + bet.stake, 0);
    const bonus = bets.filter(bet => bet.bet_type === 'bonus').reduce((sum, bet) => sum + bet.stake, 0);
    $('#atd-batch-review-summary').textContent = `${bets.length} pending straight bets · ${cash.toFixed(2)} cash at risk${bonus ? ` · ${bonus.toFixed(2)} bonus value` : ''} · ${bets[0].season} Week ${bets[0].week}`;
    $('#atd-batch-review-list').innerHTML = bets.map((bet, index) => `<div><b>${index + 1}. ${escapeHtml(bet.player_name)}</b><span>${escapeHtml(bet.team)} vs ${escapeHtml(bet.opponent)} · Yes 0.5 · ${bet.decimal_odds.toFixed(2)} odds · $${bet.stake.toFixed(2)} ${bet.bet_type}${bet.decision_context?.analyst ? ` · ${escapeHtml(bet.decision_context.analyst)}` : ''}</span></div>`).join('');
    const duplicates = new Set();
    const repeated = bets.filter(bet => { const key = `${bet.player_name.toLocaleLowerCase()}|${bet.team}|${bet.opponent}`; if (duplicates.has(key)) return true; duplicates.add(key); return false; });
    $('#atd-batch-review-warning').hidden = !repeated.length;
    $('#atd-batch-review-warning').textContent = repeated.length ? `${repeated.length} repeated player/game row(s). Check that each is a separate wager before saving.` : '';
    editPanel.hidden = true;
    reviewPanel.hidden = false;
    modal.querySelector('.modal-card').scrollTop = 0;
  }

  button.addEventListener('click', () => {
    if (!rows.children.length) addRows(10);
    if (!$('#atd-batch-week').value) {
      const season = $('#atd-batch-season').value;
      $('#atd-batch-week').value = sessionStorage.getItem(`proplens-manual-week-${season}`) || '';
    }
    modal.hidden = false;
  });
  $('#anytime-td-batch-close').addEventListener('click', () => { modal.hidden = true; });
  modal.addEventListener('click', event => { if (event.target === modal) modal.hidden = true; });
  $('#atd-batch-add-one').addEventListener('click', () => addRows(1));
  $('#atd-batch-add-ten').addEventListener('click', () => addRows(10));
  $('#atd-batch-source').addEventListener('change', () => { $('#atd-batch-analyst-label').hidden = $('#atd-batch-source').value !== 'analyst'; });
  rows.addEventListener('click', event => { if (event.target.matches('[data-remove-row]')) { event.target.closest('.atd-batch-row').remove(); renumber(); } });
  rows.addEventListener('input', event => {
    if (!event.target.matches('[data-field="player"]')) return;
    const name = event.target.value.trim();
    const sequence = ++searchSequence;
    clearTimeout(searchTimer);
    if (name.length < 2) { $('#atd-batch-player-options').replaceChildren(); return; }
    searchTimer = setTimeout(async () => {
      try {
        const [projections, directory] = await Promise.all([
          api(`/api/evaluator/players?q=${encodeURIComponent(name)}&limit=20`),
          api(`/api/player-directory/search?q=${encodeURIComponent(name)}&limit=20`),
        ]);
        if (sequence !== searchSequence) return;
        const matches = new Map();
        [...(projectionMatchesWeek(projections) ? projections.players || [] : []), ...(directory.players || [])].forEach(player => {
          const key = `${String(player.player_name || '').toLocaleLowerCase()}|${player.team}`;
          if (!matches.has(key)) matches.set(key, player);
        });
        $('#atd-batch-player-options').innerHTML = [...matches.values()].map(player => `<option value="${escapeHtml(player.player_name)}" label="${escapeHtml(player.team || '')}${player.opponent ? ` vs ${escapeHtml(player.opponent)}` : ''}"></option>`).join('');
      } catch (_) { /* Typed names remain available when suggestions cannot load. */ }
    }, 180);
  });
  rows.addEventListener('focusout', event => { if (event.target.matches('[data-field="player"]')) resolveRow(event.target.closest('.atd-batch-row')); });
  $('#atd-batch-review').addEventListener('click', async event => {
    const control = event.currentTarget;
    const used = [...rows.children].filter(usedRow);
    if (!used.length) return toast('Enter at least one bet before reviewing.', true);
    control.disabled = true;
    try { await resolveRows(used); showReview(reviewBets(used)); }
    catch (error) { toast(error.message, true); }
    finally { control.disabled = false; }
  });
  $('#atd-batch-edit-again').addEventListener('click', () => { reviewedBets = null; reviewPanel.hidden = true; editPanel.hidden = false; });
  $('#atd-batch-save').addEventListener('click', async event => {
    if (!reviewedBets?.length) return;
    const control = event.currentTarget;
    control.disabled = true;
    try {
      const result = await api('/api/tracker/bets/manual/anytime-td-batch', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ batch_id: batchId, bets: reviewedBets }) });
      modal.hidden = true;
      rows.replaceChildren();
      reviewedBets = null;
      batchId = null;
      reviewPanel.hidden = true;
      editPanel.hidden = false;
      $('#atd-batch-week').value = '';
      await window.proplensRefreshTracker?.();
      toast(`${result.count} Anytime TD bets added to the tracker.`);
    } catch (error) { toast(error.message, true); }
    finally { control.disabled = false; }
  });
})();
