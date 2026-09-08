/* Phase 4A extension: hybrid guided + free-text manual parlay tracking. */
(() => {
  const $ = selector => document.querySelector(selector);
  const trackerHeading = $('#parlay-tracker-title')?.closest('.parlay-tracker-heading');
  if (!trackerHeading) return;

  const config = window.proplensManualEntryConfig || { markets: {}, positionMarketDefaults: {} };
  const marketLabel = key => Object.values(config.markets).flat().find(([value]) => value === key)?.[1] || key || 'Other';
  const escapeHtml = value => String(value ?? '').replace(/[&<>'"]/g, character => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;' }[character]));

  trackerHeading.insertAdjacentHTML('beforeend', '<button type="button" id="btn-manual-parlay" class="manual-parlay-button">+ Track manual parlay</button>');
  document.body.insertAdjacentHTML('beforeend', `
    <div class="modal-backdrop" id="manual-parlay-modal" hidden>
      <section class="modal-card manual-parlay-card" role="dialog" aria-modal="true" aria-labelledby="manual-parlay-title">
        <button class="modal-close" data-close-manual-parlay="manual-parlay-modal" aria-label="Close">×</button>
        <p class="eyebrow">PHASE 4A · TRACKING ONLY</p>
        <div class="manual-parlay-heading">
          <div><h2 id="manual-parlay-title">Track a manual parlay</h2><p>Build common legs with guided fields, or keep unrestricted text for anything unusual.</p></div>
          <span class="manual-parlay-tag">Manual</span>
        </div>
        <form id="manual-parlay-form">
          <section class="manual-leg-section">
            <div class="manual-leg-section-title"><div><strong>Parlay legs</strong><span id="manual-parlay-leg-count">0 of 10 added</span></div><div class="manual-leg-mode" role="group" aria-label="Leg entry method"><button type="button" class="active" data-leg-mode="structured">Guided leg</button><button type="button" data-leg-mode="free_text">Free-text leg</button></div></div>
            <div id="manual-structured-leg" class="manual-leg-builder">
              <label>Category<select id="manual-leg-category"><option value="player_prop">Player prop</option><option value="game_bet">Game bet</option><option value="custom">Other / custom</option></select></label>
              <label class="manual-leg-player-field">Player<input id="manual-leg-player" class="number-input" list="manual-leg-player-options" autocomplete="off" placeholder="Type or choose an imported player"><datalist id="manual-leg-player-options"></datalist></label>
              <label class="manual-leg-player-field">Position<select id="manual-leg-position"><option value="">Optional</option><option>QB</option><option>RB</option><option>WR</option><option>TE</option><option>K</option><option>DL</option><option>LB</option><option>DB</option><option>Other</option></select></label>
              <label>Market<select id="manual-leg-market"></select></label>
              <label class="manual-leg-selection-field">Side / selection<select id="manual-leg-side"><option value="Over">Over</option><option value="Under">Under</option><option value="Yes">Yes</option><option value="No">No</option><option value="Home">Home</option><option value="Away">Away</option><option value="Other">Other</option></select></label>
              <label class="manual-leg-selection-field">Line <span>optional</span><input id="manual-leg-line" class="number-input" inputmode="decimal" placeholder="e.g. 44.5 or -3.5"></label>
              <label>Team <span>optional</span><input id="manual-leg-team" class="number-input" placeholder="e.g. PHI"></label>
              <label>Opponent <span>optional</span><input id="manual-leg-opponent" class="number-input" placeholder="e.g. DAL"></label>
              <label class="manual-leg-description">Description <span>optional override</span><input id="manual-leg-description" class="number-input" placeholder="Automatically generated if blank"></label>
              <button type="button" id="btn-add-guided-leg" class="manual-add-leg-button">Add guided leg</button>
            </div>
            <div id="manual-free-text-leg" class="manual-free-text-builder" hidden>
              <label>Leg descriptions <span>one per line</span><textarea id="manual-free-text-legs" rows="3" placeholder="T.J. Watt Over 0.5 sacks&#10;Eagles moneyline"></textarea></label>
              <button type="button" id="btn-add-free-text-legs" class="manual-add-leg-button">Add free-text leg(s)</button>
            </div>
            <div id="manual-parlay-leg-list" class="manual-parlay-leg-list"><p>No legs added yet.</p></div>
          </section>
          <div class="manual-parlay-grid manual-parlay-financials">
            <label>Description <span>optional</span><input id="manual-parlay-description" class="number-input" placeholder="e.g. Sunday games parlay"></label>
            <label>Combined decimal odds<input id="manual-parlay-odds" class="number-input" inputmode="decimal" placeholder="e.g. 5.80" required></label>
            <label>Stake / bonus value<input id="manual-parlay-stake" class="number-input" inputmode="decimal" value="5" placeholder="e.g. 10" required></label>
            <label>Bet type<select id="manual-parlay-type"><option value="cash">Cash bet</option><option value="bonus">Bonus bet — stake not returned</option></select></label>
            <label>Bet365 profit boost <span>optional %</span><input id="manual-parlay-boost" class="number-input" inputmode="decimal" min="0" placeholder="e.g. 25"></label>
            <label>Actual boosted return <span>optional $</span><input id="manual-parlay-return" class="number-input" inputmode="decimal" min="0" placeholder="Overrides boost %"></label>
            <label>Season<input id="manual-parlay-season" class="number-input" inputmode="numeric" value="2026"></label>
            <label>NFL week <span>suggested, editable</span><input id="manual-parlay-week" class="number-input" inputmode="numeric" placeholder="e.g. 1"><small class="manual-week-help" id="manual-parlay-week-help"></small></label>
            <label>Result<select id="manual-parlay-status"><option value="pending">Pending</option><option value="won">Won</option><option value="lost">Lost</option><option value="cashed_out">Cashed out</option><option value="push_adjusted">Push-adjusted</option><option value="void_adjusted">Void-adjusted</option><option value="cancelled">Cancelled before start</option></select></label>
            <label id="manual-parlay-settlement-field" hidden>Amount paid by Bet365<input id="manual-parlay-settlement" class="number-input" inputmode="decimal" min="0" placeholder="For cash-out or adjustment"></label>
          </div>
          <p class="manual-parlay-return-preview" id="manual-parlay-return-preview">Enter combined odds and stake to preview the winning return.</p>
          <p class="manual-settlement-note">This is tracking-only: no model probability, fair odds, or EV is created. Season/week applies to the full parlay only; leave both blank if its legs span different weeks.</p>
          <button class="secondary-button" id="btn-save-manual-parlay" type="submit">Save manual parlay</button>
        </form>
      </section>
    </div>`);

  const modal = $('#manual-parlay-modal');
  const form = $('#manual-parlay-form');
  const status = $('#manual-parlay-status');
  const weekHelp = $('#manual-parlay-week-help');
  const legCategory = $('#manual-leg-category');
  const legMarket = $('#manual-leg-market');
  let editingId = null;
  let draftLegs = [];
  let playerMatches = [];
  let playerSearchTimer = null;

  const value = id => $(id).value.trim();
  const numberOrNull = id => value(id) === '' ? null : Number(value(id));
  const toast = (message, error = false) => { const item = document.createElement('div'); item.className = `toast${error ? ' error' : ''}`; item.textContent = message; $('#toast-container').append(item); setTimeout(() => item.remove(), 4200); };
  async function api(url, options) { const response = await fetch(url, options); const data = await response.json().catch(() => ({})); if (!response.ok) { const detail = Array.isArray(data.detail) ? data.detail.map(item => item.msg).join(' ') : data.detail; throw new Error(detail || 'Something went wrong.'); } return data; }

  function suggestedWeekForSeason(season) { if (season !== 2026) return null; const start = new Date(2026, 8, 9); const today = new Date(); today.setHours(0, 0, 0, 0); const days = Math.floor((today - start) / 86400000); const week = Math.floor((days + 1) / 7) + 1; return week >= 1 && week <= 18 ? week : null; }
  function applyWeekSuggestion() { const season = Number(value('#manual-parlay-season')); const stored = Number(sessionStorage.getItem(`proplens-manual-week-${season}`)); const suggested = Number.isInteger(stored) && stored >= 1 && stored <= 25 ? stored : suggestedWeekForSeason(season); $('#manual-parlay-week').value = suggested || ''; weekHelp.textContent = stored ? `Using Week ${stored}, your last choice this session.` : suggested ? `Suggested Week ${suggested} from today's NFL calendar. You can change it.` : 'Choose the week manually for this season.'; }
  function rememberWeek() { const season = Number(value('#manual-parlay-season')), week = Number(value('#manual-parlay-week')); if (!Number.isInteger(season) || !Number.isInteger(week) || week < 1 || week > 25) return; sessionStorage.setItem(`proplens-manual-week-${season}`, String(week)); weekHelp.textContent = `Week ${week} will be used for new manual bets this session.`; }
  function updateSettlementVisibility() { $('#manual-parlay-settlement-field').hidden = !['cashed_out', 'push_adjusted', 'void_adjusted'].includes(status.value); }
  function updateReturnPreview() { const odds = numberOrNull('#manual-parlay-odds'), stake = numberOrNull('#manual-parlay-stake'), boost = numberOrNull('#manual-parlay-boost') || 0, actual = numberOrNull('#manual-parlay-return'); const preview = $('#manual-parlay-return-preview'); if (!odds || odds <= 1 || !stake || stake <= 0) { preview.textContent = 'Enter combined odds and stake to preview the winning return.'; return; } const effective = 1 + (odds - 1) * (1 + boost / 100); const totalReturn = actual ?? stake * effective; preview.textContent = actual !== null ? `Exact winning return: $${totalReturn.toFixed(2)} (your override).` : `Winning return: $${totalReturn.toFixed(2)} at ${effective.toFixed(2)} effective odds.`; }

  function setLegMode(mode) {
    document.querySelectorAll('[data-leg-mode]').forEach(button => button.classList.toggle('active', button.dataset.legMode === mode));
    $('#manual-structured-leg').hidden = mode !== 'structured';
    $('#manual-free-text-leg').hidden = mode !== 'free_text';
  }

  function renderLegMarkets(selected = '') {
    const options = config.markets[legCategory.value] || [['custom', 'Other / custom bet']];
    legMarket.innerHTML = options.map(([key, label]) => `<option value="${escapeHtml(key)}">${escapeHtml(label)}</option>`).join('');
    if (selected && [...legMarket.options].some(option => option.value === selected)) legMarket.value = selected;
    document.querySelectorAll('.manual-leg-player-field').forEach(field => field.hidden = legCategory.value !== 'player_prop');
    document.querySelectorAll('.manual-leg-selection-field').forEach(field => field.hidden = legCategory.value === 'custom');
    if (!selected) $('#manual-leg-side').value = legCategory.value === 'game_bet' ? 'Home' : legCategory.value === 'custom' ? 'Other' : 'Over';
  }

  function applyDefaultLegMarket() {
    const defaultMarket = config.positionMarketDefaults[$('#manual-leg-position').value];
    if (defaultMarket && [...legMarket.options].some(option => option.value === defaultMarket)) legMarket.value = defaultMarket;
  }

  async function searchLegPlayers() {
    const query = value('#manual-leg-player');
    try {
      const data = await api(`/api/evaluator/players?q=${encodeURIComponent(query)}&limit=20`);
      playerMatches = data.players || [];
      $('#manual-leg-player-options').innerHTML = playerMatches.map(player => `<option value="${escapeHtml(player.player_name)}">${escapeHtml(player.team)} · ${escapeHtml(player.position)}</option>`).join('');
      applyLegPlayerSuggestion();
    } catch (_) { playerMatches = []; }
  }

  function applyLegPlayerSuggestion() {
    const typed = value('#manual-leg-player').toLowerCase();
    const match = playerMatches.find(player => player.player_name.toLowerCase() === typed);
    if (!match) return;
    $('#manual-leg-team').value = match.team || '';
    $('#manual-leg-opponent').value = match.opponent || '';
    $('#manual-leg-position').value = match.position || '';
    applyDefaultLegMarket();
  }

  function generatedLegDescription() {
    const category = legCategory.value;
    const subject = category === 'player_prop' ? value('#manual-leg-player') : [value('#manual-leg-team'), value('#manual-leg-opponent') ? `vs ${value('#manual-leg-opponent')}` : ''].filter(Boolean).join(' ');
    const side = category === 'custom' ? '' : value('#manual-leg-side');
    const line = category === 'custom' ? '' : value('#manual-leg-line');
    return [subject, side, line, marketLabel(legMarket.value)].filter(Boolean).join(' · ');
  }

  function renderDraftLegs() {
    $('#manual-parlay-leg-count').textContent = `${draftLegs.length} of 10 added`;
    $('#manual-parlay-leg-list').innerHTML = draftLegs.length ? draftLegs.map((leg, index) => `<article><div><strong>${escapeHtml(leg.description)}</strong><small>${leg.entry_mode === 'structured' ? 'Guided leg' : 'Free-text leg'}${leg.team ? ` · ${escapeHtml(leg.team)}${leg.opponent ? ` vs ${escapeHtml(leg.opponent)}` : ''}` : ''}</small></div><button type="button" data-remove-manual-leg="${index}" aria-label="Remove ${escapeHtml(leg.description)}">Remove</button></article>`).join('') : '<p>No legs added yet. Add at least two before saving.</p>';
  }

  function addGuidedLeg() {
    if (draftLegs.length >= 10) return toast('A manual parlay can contain up to 10 legs.', true);
    const category = legCategory.value;
    const description = value('#manual-leg-description') || generatedLegDescription();
    if (!description) return toast(category === 'player_prop' ? 'Choose or type a player.' : 'Enter enough details to describe this leg.', true);
    draftLegs.push({ entry_mode: 'structured', description, category, player_name: category === 'player_prop' ? value('#manual-leg-player') || null : null, position: category === 'player_prop' ? value('#manual-leg-position') || null : null, team: value('#manual-leg-team') || null, opponent: value('#manual-leg-opponent') || null, market: legMarket.value || null, side_label: category === 'custom' ? null : value('#manual-leg-side') || null, line: category === 'custom' ? null : numberOrNull('#manual-leg-line') });
    $('#manual-leg-description').value = ''; $('#manual-leg-line').value = ''; if (category === 'player_prop') $('#manual-leg-player').value = '';
    renderDraftLegs();
  }

  function addFreeTextLegs() {
    const descriptions = value('#manual-free-text-legs').split(/\r?\n/).map(item => item.trim()).filter(Boolean);
    if (!descriptions.length) return toast('Enter at least one free-text leg.', true);
    if (draftLegs.length + descriptions.length > 10) return toast('A manual parlay can contain up to 10 legs.', true);
    draftLegs.push(...descriptions.map(description => ({ entry_mode: 'free_text', description })));
    $('#manual-free-text-legs').value = ''; renderDraftLegs();
  }

  function resetForm() {
    form.reset(); editingId = null; draftLegs = []; $('#manual-parlay-season').value = '2026'; status.value = 'pending'; legCategory.value = 'player_prop';
    renderLegMarkets(); setLegMode('structured'); renderDraftLegs(); applyWeekSuggestion(); updateSettlementVisibility(); updateReturnPreview();
    $('#manual-parlay-title').textContent = 'Track a manual parlay'; $('#btn-save-manual-parlay').textContent = 'Save manual parlay';
  }

  function payload() {
    const season = numberOrNull('#manual-parlay-season'), week = numberOrNull('#manual-parlay-week'), settlement = numberOrNull('#manual-parlay-settlement');
    if (draftLegs.length < 2) throw new Error('Add at least two parlay legs.');
    if ((season === null) !== (week === null)) throw new Error('Enter both season and NFL week, or leave both blank.');
    if (['cashed_out', 'push_adjusted', 'void_adjusted'].includes(status.value) && settlement === null) throw new Error('Enter the actual amount paid by Bet365.');
    return { description: value('#manual-parlay-description') || null, legs: draftLegs, decimal_odds: Number(value('#manual-parlay-odds')), stake: Number(value('#manual-parlay-stake')), bet_type: value('#manual-parlay-type'), profit_boost_pct: numberOrNull('#manual-parlay-boost') || 0, actual_total_return: numberOrNull('#manual-parlay-return'), season, week, status: status.value, settlement_amount: settlement };
  }

  function openForEdit(parlay) {
    editingId = parlay.id;
    draftLegs = parlay.legs.map(leg => ({ entry_mode: leg.entry_mode || (leg.market === 'manual' ? 'free_text' : 'structured'), description: leg.description || leg.player_name, category: leg.category || null, player_name: leg.entry_mode === 'structured' ? leg.player_name : null, position: leg.position || leg.result_identity?.position || null, team: leg.team || null, opponent: leg.opponent || null, market: leg.market === 'manual' ? null : leg.market, side_label: leg.side_label || null, line: leg.line ?? null }));
    $('#manual-parlay-description').value = parlay.description || ''; $('#manual-parlay-odds').value = parlay.original_decimal_odds; $('#manual-parlay-stake').value = parlay.stake; $('#manual-parlay-type').value = parlay.bet_type; $('#manual-parlay-boost').value = parlay.profit_boost_pct || ''; $('#manual-parlay-return').value = parlay.actual_total_return ?? ''; $('#manual-parlay-season').value = parlay.season ?? ''; $('#manual-parlay-week').value = parlay.week ?? ''; status.value = parlay.status; $('#manual-parlay-settlement').value = parlay.settlement_amount ?? '';
    weekHelp.textContent = parlay.week ? `Saved Week ${parlay.week}. Editing does not change it automatically.` : 'No NFL week was saved for this record.';
    $('#manual-parlay-title').textContent = 'Edit manual parlay'; $('#btn-save-manual-parlay').textContent = 'Save changes'; renderDraftLegs(); updateSettlementVisibility(); updateReturnPreview(); modal.hidden = false;
  }

  $('#btn-manual-parlay').addEventListener('click', () => { resetForm(); modal.hidden = false; searchLegPlayers(); });
  document.addEventListener('click', event => {
    const closeButton = event.target.closest('[data-close-manual-parlay]'); if (closeButton) modal.hidden = true;
    const modeButton = event.target.closest('[data-leg-mode]'); if (modeButton) setLegMode(modeButton.dataset.legMode);
    const removeButton = event.target.closest('[data-remove-manual-leg]'); if (removeButton) { draftLegs.splice(Number(removeButton.dataset.removeManualLeg), 1); renderDraftLegs(); }
    const editButton = event.target.closest('[data-manual-parlay-edit]'); if (!editButton) return;
    const parlay = (window.proplensTrackedParlays || []).find(item => item.id === editButton.dataset.manualParlayEdit); if (parlay) openForEdit(parlay);
  });
  modal.addEventListener('click', event => { if (event.target === modal) modal.hidden = true; });
  $('#btn-add-guided-leg').addEventListener('click', addGuidedLeg); $('#btn-add-free-text-legs').addEventListener('click', addFreeTextLegs);
  legCategory.addEventListener('change', () => renderLegMarkets()); $('#manual-leg-position').addEventListener('change', applyDefaultLegMarket);
  $('#manual-leg-player').addEventListener('input', () => { applyLegPlayerSuggestion(); clearTimeout(playerSearchTimer); playerSearchTimer = setTimeout(searchLegPlayers, 180); });
  ['#manual-parlay-odds', '#manual-parlay-stake', '#manual-parlay-boost', '#manual-parlay-return'].forEach(id => $(id).addEventListener('input', updateReturnPreview));
  status.addEventListener('change', updateSettlementVisibility); $('#manual-parlay-season').addEventListener('change', applyWeekSuggestion); $('#manual-parlay-week').addEventListener('change', rememberWeek);
  form.addEventListener('submit', async event => {
    event.preventDefault(); const button = $('#btn-save-manual-parlay'); button.disabled = true;
    try { const body = payload(); const url = editingId ? `/api/tracker/parlays/${editingId}/manual` : '/api/tracker/parlays/manual'; await api(url, { method: editingId ? 'PUT' : 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }); modal.hidden = true; await window.proplensRefreshParlayTracker?.(); toast(editingId ? 'Manual parlay updated.' : 'Manual parlay added to the tracker.'); }
    catch (error) { toast(error.message, true); } finally { button.disabled = false; }
  });
})();
