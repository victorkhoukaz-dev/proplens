/* Phase 4A extension: hybrid guided + free-text manual parlay tracking. */
(() => {
  const $ = selector => document.querySelector(selector);
  const slipActions = $('#parlay-modal .parlay-heading-actions');
  if (!slipActions) return;

  const config = window.proplensManualEntryConfig || { markets: {}, positionMarketDefaults: {} };
  const marketLabel = key => Object.values(config.markets).flat().find(([value]) => value === key)?.[1] || key || 'Other';
  const escapeHtml = value => String(value ?? '').replace(/[&<>'"]/g, character => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;' }[character]));

  slipActions.insertAdjacentHTML('afterbegin', '<button type="button" id="btn-manual-parlay" class="parlay-sensitivity-toggle">Track manual parlay</button>');
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
              <label class="manual-leg-player-field">Player<input id="manual-leg-player" class="number-input" list="manual-leg-player-options" autocomplete="off" placeholder="Type or choose a player"><datalist id="manual-leg-player-options"></datalist><small class="manual-player-source" id="manual-leg-player-source"></small></label>
              <label class="manual-leg-player-field">Position<select id="manual-leg-position"><option value="">Optional</option><option>QB</option><option>RB</option><option>WR</option><option>TE</option><option>K</option><option>EDGE</option><option>DL</option><option>LB</option><option>DB</option><option>Other</option></select></label>
              <label>Market<select id="manual-leg-market"></select></label>
              <label class="manual-leg-selection-field">Side / selection<select id="manual-leg-side"><option value="Over">Over</option><option value="Under">Under</option><option value="Yes">Yes</option><option value="No">No</option><option value="Home">Home</option><option value="Away">Away</option><option value="Other">Other</option></select></label>
              <label class="manual-leg-selection-field">Line <span>optional</span><input id="manual-leg-line" class="number-input" inputmode="decimal" placeholder="e.g. 44.5 or -3.5"></label>
              <label class="manual-leg-player-field">Decimal odds <span>optional</span><input id="manual-leg-odds" class="number-input" inputmode="decimal" min="1.01" placeholder="e.g. 1.90"><small>Saved for a later projection evaluation.</small></label>
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
            <button type="button" id="manual-leg-edit-cancel" class="manual-leg-edit-cancel" hidden>Cancel leg edit</button>
          </section>
          <div class="manual-parlay-grid manual-parlay-financials">
            <label>Description <span>optional</span><input id="manual-parlay-description" class="number-input" placeholder="e.g. Sunday games parlay"></label>
            <label>Combined decimal odds<input id="manual-parlay-odds" class="number-input" inputmode="decimal" placeholder="e.g. 5.80" required></label>
            <label>Stake / bonus value<input id="manual-parlay-stake" class="number-input" inputmode="decimal" value="5" placeholder="e.g. 10" required></label>
            <label>Bet type<select id="manual-parlay-type"><option value="cash">Cash bet</option><option value="bonus">Bonus bet — stake not returned</option></select></label>
            <label>Bet365 profit boost <span>optional %</span><input id="manual-parlay-boost" class="number-input" inputmode="decimal" min="0" placeholder="e.g. 25"></label>
            <label id="manual-parlay-return-label">Actual total return <span>optional $</span><input id="manual-parlay-return" class="number-input" inputmode="decimal" min="0" placeholder="Overrides boost %"></label>
            <label>Season<input id="manual-parlay-season" class="number-input" inputmode="numeric" value="2026"></label>
            <label>NFL week <span>suggested, editable</span><input id="manual-parlay-week" class="number-input" inputmode="numeric" placeholder="e.g. 1"><small class="manual-week-help" id="manual-parlay-week-help"></small></label>
            <label>Result<select id="manual-parlay-status"><option value="pending">Pending</option><option value="won">Won</option><option value="lost">Lost</option><option value="cashed_out">Cashed out</option><option value="push_adjusted">Push-adjusted</option><option value="void_adjusted">Void-adjusted</option><option value="cancelled" hidden>Cancelled before start (legacy)</option></select></label>
            <label id="manual-parlay-settlement-field" hidden>Amount paid by Bet365<input id="manual-parlay-settlement" class="number-input" inputmode="decimal" min="0" placeholder="For cash-out or adjustment"></label>
          </div>
          <fieldset class="decision-context"><legend>Decision context <span>optional</span></legend><label>Decision source<select id="manual-parlay-decision-source"><option value="">No note</option><option value="model">Model only</option><option value="analyst">Analyst recommendation</option><option value="hedge">Hedge</option><option value="own_analysis">My own analysis</option><option value="other">Other</option></select></label><label id="manual-parlay-analyst-label" hidden>Analyst<input id="manual-parlay-analyst" class="number-input" list="analyst-options" placeholder="e.g. Chris Wecht"></label><label>Note <span>optional</span><textarea id="manual-parlay-decision-note" rows="2" placeholder="Why you placed this parlay"></textarea></label></fieldset>
          <p class="manual-parlay-return-preview" id="manual-parlay-return-preview">Enter combined odds and stake to preview the result.</p>
          <p class="manual-settlement-note">This is tracking-only: no model probability, fair odds, or EV is created. Season/week applies to the full parlay only; leave both blank if its legs span different weeks.</p>
          <button class="secondary-button" id="btn-save-manual-parlay" type="submit">Save manual parlay</button>
        </form>
      </section>
    </div>`);

  const modal = $('#manual-parlay-modal');
  const form = $('#manual-parlay-form');
  modal.querySelector('.manual-parlay-heading').insertAdjacentHTML('afterend', `
    <section class="ticket-import" aria-label="Import placed parlay screenshot">
      <div><strong>Have a screenshot of the placed parlay?</strong><span>Read one ticket locally, then correct the draft below before saving.</span></div>
      <div class="ticket-import-controls"><input id="manual-parlay-screenshot" type="file" accept="image/png,image/jpeg,image/webp" aria-label="Parlay ticket screenshot"><button type="button" id="btn-read-parlay-screenshot">Read screenshot into draft</button></div>
      <p id="ticket-import-status" class="field-help" aria-live="polite">Nothing is saved by reading a screenshot. Individual leg odds can stay blank.</p>
      <div id="ticket-import-review" hidden><img id="ticket-import-image" alt="Uploaded parlay screenshot for comparison"><div><strong>Check against your screenshot</strong><ul id="ticket-import-warnings"></ul><details><summary>Show text read from screenshot</summary><pre id="ticket-import-raw-text"></pre></details></div></div>
    </section>`);
  $('#btn-save-manual-parlay').insertAdjacentHTML('beforebegin', '<label class="ticket-import-confirm" id="ticket-import-confirm-label" hidden><input type="checkbox" id="ticket-import-confirm"> I checked every leg, combined odds, stake, and cash/bonus type against the screenshot.</label>');
  $('#manual-parlay-type').insertAdjacentHTML('afterbegin', '<option value="">Choose cash or bonus</option>');
  const status = $('#manual-parlay-status');
  const weekHelp = $('#manual-parlay-week-help');
  const legCategory = $('#manual-leg-category');
  const legMarket = $('#manual-leg-market');
  let editingId = null;
  let draftLegs = [];
  let editingLegIndex = null;
  let playerMatches = [];
  let playerSearchTimer = null;
  let screenshotDraft = false;
  let screenshotObjectUrl = null;
  const safetyNet = window.proplensSafetyNet.mount($('.manual-parlay-financials'), {stake: () => Number($('#manual-parlay-stake').value), type: () => $('#manual-parlay-type').value, changed: updateReturnPreview});
  const safetyPreview = document.createElement('div'); safetyNet.root.insertAdjacentElement('afterend', safetyPreview);
  const syncDecisionContext = () => { $('#manual-parlay-analyst-label').hidden = $('#manual-parlay-decision-source').value !== 'analyst'; };

  const value = id => $(id).value.trim();
  const numberOrNull = id => value(id) === '' ? null : Number(value(id));
  const toast = (message, error = false) => { const item = document.createElement('div'); item.className = `toast${error ? ' error' : ''}`; item.textContent = message; $('#toast-container').append(item); setTimeout(() => item.remove(), 4200); };
  async function api(url, options) { const response = await fetch(url, options); const data = await response.json().catch(() => ({})); if (!response.ok) { const detail = Array.isArray(data.detail) ? data.detail.map(item => item.msg).join(' ') : data.detail; throw new Error(detail || 'Something went wrong.'); } return data; }

  function suggestedWeekForSeason(season) { if (season !== 2026) return null; const start = new Date(2026, 8, 9); const today = new Date(); today.setHours(0, 0, 0, 0); const days = Math.floor((today - start) / 86400000); const week = Math.floor((days + 1) / 7) + 1; return week >= 1 && week <= 18 ? week : null; }
  function applyWeekSuggestion() { const season = Number(value('#manual-parlay-season')); const stored = Number(sessionStorage.getItem(`proplens-manual-week-${season}`)); const suggested = Number.isInteger(stored) && stored >= 1 && stored <= 25 ? stored : suggestedWeekForSeason(season); $('#manual-parlay-week').value = suggested || ''; weekHelp.textContent = stored ? `Using Week ${stored}, your last choice this session.` : suggested ? `Suggested Week ${suggested} from today's NFL calendar. You can change it.` : 'Choose the week manually for this season.'; }
  function rememberWeek() { const season = Number(value('#manual-parlay-season')), week = Number(value('#manual-parlay-week')); if (!Number.isInteger(season) || !Number.isInteger(week) || week < 1 || week > 25) return; sessionStorage.setItem(`proplens-manual-week-${season}`, String(week)); weekHelp.textContent = `Week ${week} will be used for new manual bets this session.`; }
  function updateSettlementVisibility() { $('#manual-parlay-settlement-field').hidden = !['cashed_out', 'push_adjusted', 'void_adjusted'].includes(status.value); }
  function updateReturnPreview() { safetyNet.sync(); safetyPreview.innerHTML = ''; const odds = numberOrNull('#manual-parlay-odds'), stake = numberOrNull('#manual-parlay-stake'), boost = numberOrNull('#manual-parlay-boost') || 0, actual = numberOrNull('#manual-parlay-return'); const preview = $('#manual-parlay-return-preview'), isBonus = value('#manual-parlay-type') === 'bonus'; $('#manual-parlay-return-label').firstChild.textContent = isBonus ? 'Actual cash payout ' : 'Actual total return '; if (!value('#manual-parlay-type')) { preview.textContent = 'Choose cash or bonus before checking the payout.'; return; } if (!odds || odds <= 1 || !stake || stake <= 0) { preview.textContent = 'Enter combined odds and stake to preview the result.'; return; } const effective = 1 + (odds - 1) * (1 + boost / 100); const payout = actual ?? stake * (isBonus ? effective - 1 : effective); const label = isBonus ? 'Potential cash payout' : 'Winning total return'; preview.textContent = actual !== null ? `${isBonus ? 'Exact cash payout' : 'Exact winning total return'}: $${payout.toFixed(2)} (your override).` : `${label}: $${payout.toFixed(2)} at ${effective.toFixed(2)} effective odds.${isBonus ? ' Bonus stake is not returned.' : ''}`; try { safetyPreview.innerHTML = window.proplensSafetyNet.result(safetyNet.value(), stake, payout); } catch (error) { safetyPreview.textContent = error.message; } }

  function clearScreenshotReview() {
    screenshotDraft = false;
    if (screenshotObjectUrl) URL.revokeObjectURL(screenshotObjectUrl);
    screenshotObjectUrl = null;
    $('#manual-parlay-screenshot').value = '';
    $('#ticket-import-image').removeAttribute('src');
    $('#ticket-import-review').hidden = true;
    $('#ticket-import-confirm-label').hidden = true;
    $('#ticket-import-confirm').checked = false;
    $('#ticket-import-status').textContent = 'Nothing is saved by reading a screenshot. Individual leg odds can stay blank.';
  }

  async function readParlayScreenshot() {
    const file = $('#manual-parlay-screenshot').files[0];
    if (!file) return toast('Choose one screenshot of the placed parlay.', true);
    if (editingId || draftLegs.length || value('#manual-parlay-odds') || (value('#manual-parlay-stake') && value('#manual-parlay-stake') !== '5')) return toast('Start a new blank manual parlay before importing a screenshot.', true);
    const button = $('#btn-read-parlay-screenshot');
    button.disabled = true;
    $('#ticket-import-status').textContent = 'Reading the ticket locally…';
    try {
      const formData = new FormData();
      formData.append('file', file);
      const result = await api('/api/parlay-screenshots/extract', { method: 'POST', body: formData });
      const draft = result.draft;
      draftLegs = draft.legs.slice(0, 10);
      $('#manual-parlay-odds').value = draft.combined_odds ?? '';
      $('#manual-parlay-stake').value = draft.stake ?? '';
      $('#manual-parlay-type').value = draft.bet_type || '';
      screenshotDraft = true;
      $('#ticket-import-confirm-label').hidden = false;
      $('#ticket-import-confirm').checked = false;
      if (screenshotObjectUrl) URL.revokeObjectURL(screenshotObjectUrl);
      screenshotObjectUrl = URL.createObjectURL(file);
      $('#ticket-import-image').src = screenshotObjectUrl;
      $('#ticket-import-warnings').innerHTML = (draft.warnings.length ? draft.warnings : ['Every extracted field still needs your review.']).map(warning => `<li>${escapeHtml(warning)}</li>`).join('');
      $('#ticket-import-raw-text').textContent = result.raw_text || 'No readable text found.';
      $('#ticket-import-review').hidden = false;
      $('#ticket-import-status').textContent = `${draftLegs.length} leg${draftLegs.length === 1 ? '' : 's'} prefilled. Correct or add legs below, then confirm the ticket details before saving.`;
      renderDraftLegs(); updateReturnPreview();
    } catch (error) { $('#ticket-import-status').textContent = error.message; toast(error.message, true); }
    finally { button.disabled = false; }
  }

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

  function syncAnytimeTouchdownLeg() {
    const anytime = legMarket.value === 'anytime_td';
    const side = $('#manual-leg-side'), line = $('#manual-leg-line');
    if (anytime) { side.value = 'Yes'; line.value = '0.5'; }
    side.disabled = anytime; line.readOnly = anytime;
  }

  async function searchLegPlayers() {
    const query = value('#manual-leg-player');
    try {
      const [projectionData, directoryData] = await Promise.all([
        api(`/api/evaluator/players?q=${encodeURIComponent(query)}&limit=20&include_projection_only=true`),
        api(`/api/player-directory/search?q=${encodeURIComponent(query)}&limit=20`),
      ]);
      const projectionPlayers = (projectionData.players || []).map(player => ({ ...player, source: 'projection' }));
      const projectionKeys = new Set(projectionPlayers.map(player => `${String(player.player_name).toLowerCase()}|${player.team}`));
      const directoryPlayers = (directoryData.players || [])
        .filter(player => !projectionKeys.has(`${String(player.player_name).toLowerCase()}|${player.team}`))
        .map(player => ({ ...player, source: 'directory', markets: [] }));
      playerMatches = [...projectionPlayers, ...directoryPlayers];
      $('#manual-leg-player-options').innerHTML = playerMatches.map(player => `<option value="${escapeHtml(player.player_name)}">${escapeHtml(player.team)} · ${escapeHtml(player.position)} · ${player.source === 'projection' ? (player.projection_only ? 'Defensive projection' : 'Active projection') : 'Player directory — no projection'}</option>`).join('');
      applyLegPlayerSuggestion();
    } catch (_) { playerMatches = []; $('#manual-leg-player-options').innerHTML = ''; }
  }

  function applyLegPlayerSuggestion() {
    const typed = value('#manual-leg-player').toLowerCase();
    const match = playerMatches.find(player => player.player_name.toLowerCase() === typed);
    const source = $('#manual-leg-player-source');
    if (!match) { source.textContent = ''; source.classList.remove('directory'); return; }
    $('#manual-leg-team').value = match.team || '';
    if (match.source === 'projection') $('#manual-leg-opponent').value = match.opponent || '';
    const positionOption = [...$('#manual-leg-position').options].find(option => option.value === match.position);
    $('#manual-leg-position').value = positionOption ? match.position : 'Other';
    applyDefaultLegMarket();
    source.textContent = match.source === 'projection' ? (match.projection_only ? 'Defensive projection found. This remains a tracking-only manual parlay leg.' : 'Active projection match — use the evaluator when you are ready.') : 'Player directory — no projection loaded. This remains a tracking-only manual parlay leg.';
    source.classList.toggle('directory', match.source === 'directory');
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
    $('#manual-parlay-leg-list').innerHTML = draftLegs.length ? draftLegs.map((leg, index) => `<article><div><strong>${escapeHtml(leg.description)}</strong><small>${leg.entry_mode === 'structured' ? 'Guided leg' : 'Free-text leg'}${leg.team ? ` · ${escapeHtml(leg.team)}${leg.opponent ? ` vs ${escapeHtml(leg.opponent)}` : ''}` : ''}${Number.isFinite(leg.decimal_odds) ? ` · ${leg.decimal_odds.toFixed(2)} odds` : ''}</small></div><span class="manual-leg-actions"><button type="button" data-edit-manual-leg="${index}" aria-label="Edit ${escapeHtml(leg.description)}">Edit</button><button type="button" data-remove-manual-leg="${index}" aria-label="Remove ${escapeHtml(leg.description)}">Remove</button></span></article>`).join('') : '<p>No legs added yet. Add at least two before saving.</p>';
  }

  function stopLegEdit() {
    editingLegIndex = null;
    $('#btn-add-guided-leg').textContent = 'Add guided leg';
    $('#btn-add-free-text-legs').textContent = 'Add free-text leg(s)';
    $('#manual-leg-edit-cancel').hidden = true;
  }

  function editDraftLeg(index) {
    const leg = draftLegs[index]; if (!leg) return;
    editingLegIndex = index;
    $('#manual-leg-edit-cancel').hidden = false;
    if (leg.entry_mode === 'free_text') {
      setLegMode('free_text'); $('#manual-free-text-legs').value = leg.description;
      $('#btn-add-free-text-legs').textContent = 'Save this leg';
      $('#manual-free-text-legs').focus();
    } else {
      setLegMode('structured'); legCategory.value = leg.category || 'player_prop'; renderLegMarkets(leg.market);
      $('#manual-leg-player').value = leg.player_name || ''; $('#manual-leg-position').value = leg.position || '';
      $('#manual-leg-team').value = leg.team || ''; $('#manual-leg-opponent').value = leg.opponent || '';
      $('#manual-leg-side').value = leg.side_label || 'Over'; $('#manual-leg-line').value = leg.line ?? '';
      $('#manual-leg-odds').value = leg.decimal_odds ?? ''; $('#manual-leg-description').value = leg.description === generatedLegDescription() ? '' : leg.description || '';
      $('#btn-add-guided-leg').textContent = 'Save this leg';
      $('#manual-leg-player').focus();
    }
  }

  function addGuidedLeg() {
    if (editingLegIndex === null && draftLegs.length >= 10) return toast('A manual parlay can contain up to 10 legs.', true);
    const category = legCategory.value;
    const description = value('#manual-leg-description') || generatedLegDescription();
    if (!description) return toast(category === 'player_prop' ? 'Choose or type a player.' : 'Enter enough details to describe this leg.', true);
    const decimalOdds = numberOrNull('#manual-leg-odds');
    if (decimalOdds !== null && (!Number.isFinite(decimalOdds) || decimalOdds <= 1)) return toast('Enter decimal odds above 1.00, or leave the field blank.', true);
    const leg = { entry_mode: 'structured', description, category, player_name: category === 'player_prop' ? value('#manual-leg-player') || null : null, position: category === 'player_prop' ? value('#manual-leg-position') || null : null, team: value('#manual-leg-team') || null, opponent: value('#manual-leg-opponent') || null, market: legMarket.value || null, side_label: category === 'custom' ? null : value('#manual-leg-side') || null, line: category === 'custom' ? null : numberOrNull('#manual-leg-line'), decimal_odds: decimalOdds };
    if (editingLegIndex === null) draftLegs.push(leg); else draftLegs[editingLegIndex] = leg;
    stopLegEdit();
    $('#manual-leg-description').value = ''; $('#manual-leg-line').value = ''; $('#manual-leg-odds').value = ''; if (category === 'player_prop') $('#manual-leg-player').value = '';
    renderDraftLegs();
  }

  function addFreeTextLegs() {
    const descriptions = value('#manual-free-text-legs').split(/\r?\n/).map(item => item.trim()).filter(Boolean);
    if (!descriptions.length) return toast('Enter at least one free-text leg.', true);
    if (editingLegIndex !== null && descriptions.length !== 1) return toast('Edit one free-text leg at a time.', true);
    if (draftLegs.length + descriptions.length > 10 && editingLegIndex === null) return toast('A manual parlay can contain up to 10 legs.', true);
    if (editingLegIndex === null) draftLegs.push(...descriptions.map(description => ({ entry_mode: 'free_text', description })));
    else draftLegs[editingLegIndex] = { entry_mode: 'free_text', description: descriptions[0] };
    stopLegEdit();
    $('#manual-free-text-legs').value = ''; renderDraftLegs();
  }

  function resetForm() {
    form.reset(); clearScreenshotReview(); safetyNet.set(null); editingId = null; draftLegs = []; stopLegEdit(); $('#manual-parlay-season').value = '2026'; $('#manual-parlay-type').value = 'cash'; status.value = 'pending'; legCategory.value = 'player_prop';
    $('#manual-leg-player-source').textContent = ''; $('#manual-leg-player-source').classList.remove('directory');
    renderLegMarkets(); setLegMode('structured'); renderDraftLegs(); applyWeekSuggestion(); updateSettlementVisibility(); updateReturnPreview();
    syncDecisionContext();
    $('#manual-parlay-title').textContent = 'Track a manual parlay'; $('#btn-save-manual-parlay').textContent = 'Save manual parlay';
  }

  function payload() {
    const season = numberOrNull('#manual-parlay-season'), week = numberOrNull('#manual-parlay-week'), settlement = numberOrNull('#manual-parlay-settlement');
    if (draftLegs.length < 2) throw new Error('Add at least two parlay legs.');
    if (!value('#manual-parlay-type')) throw new Error('Choose whether this was a cash or bonus bet.');
    if (screenshotDraft && !$('#ticket-import-confirm').checked) throw new Error('Review the screenshot and check the confirmation box before saving.');
    if ((season === null) !== (week === null)) throw new Error('Enter both season and NFL week, or leave both blank.');
    if (['cashed_out', 'push_adjusted', 'void_adjusted'].includes(status.value) && settlement === null) throw new Error('Enter the actual amount paid by Bet365.');
    const source = value('#manual-parlay-decision-source'), analyst = value('#manual-parlay-analyst'), note = value('#manual-parlay-decision-note');
    if (source === 'analyst' && !analyst) throw new Error('Choose or enter the analyst who recommended this parlay.');
    return { safety_net: safetyNet.value(), description: value('#manual-parlay-description') || null, decision_context: source ? { source, ...(source === 'analyst' ? { analyst } : {}), ...(note ? { note } : {}) } : null, legs: draftLegs, decimal_odds: Number(value('#manual-parlay-odds')), stake: Number(value('#manual-parlay-stake')), bet_type: value('#manual-parlay-type'), profit_boost_pct: numberOrNull('#manual-parlay-boost') || 0, actual_total_return: numberOrNull('#manual-parlay-return'), season, week, status: status.value, settlement_amount: settlement };
  }

  function openForEdit(parlay) {
    clearScreenshotReview();
    stopLegEdit();
    editingId = parlay.id;
    draftLegs = parlay.legs.map(leg => ({ entry_mode: leg.entry_mode || (leg.market === 'manual' ? 'free_text' : 'structured'), description: leg.description || leg.player_name, category: leg.category || null, player_name: leg.entry_mode === 'structured' ? leg.player_name : null, position: leg.position || leg.result_identity?.position || null, team: leg.team || null, opponent: leg.opponent || null, market: leg.market === 'manual' ? null : leg.market, side_label: leg.side_label || null, line: leg.line ?? null, decimal_odds: leg.decimal_odds ?? null }));
    $('#manual-parlay-description').value = parlay.description || ''; $('#manual-parlay-odds').value = parlay.original_decimal_odds; $('#manual-parlay-stake').value = parlay.stake; $('#manual-parlay-type').value = parlay.bet_type; $('#manual-parlay-boost').value = parlay.profit_boost_pct || ''; $('#manual-parlay-return').value = parlay.actual_total_return ?? ''; $('#manual-parlay-season').value = parlay.season ?? ''; $('#manual-parlay-week').value = parlay.week ?? ''; status.value = parlay.status; $('#manual-parlay-settlement').value = parlay.settlement_amount ?? '';
    $('#manual-parlay-decision-source').value = parlay.decision_context?.source || ''; $('#manual-parlay-analyst').value = parlay.decision_context?.analyst || ''; $('#manual-parlay-decision-note').value = parlay.decision_context?.note || ''; syncDecisionContext();
    safetyNet.set(parlay.safety_net);
    weekHelp.textContent = parlay.week ? `Saved Week ${parlay.week}. Editing does not change it automatically.` : 'No NFL week was saved for this record.';
    $('#manual-parlay-title').textContent = 'Edit manual parlay'; $('#btn-save-manual-parlay').textContent = 'Save changes'; renderDraftLegs(); updateSettlementVisibility(); updateReturnPreview(); modal.hidden = false;
  }

  $('#btn-manual-parlay').addEventListener('click', () => { resetForm(); modal.hidden = false; searchLegPlayers(); });
  $('#btn-read-parlay-screenshot').addEventListener('click', readParlayScreenshot);
  $('#manual-leg-edit-cancel').addEventListener('click', () => { stopLegEdit(); $('#manual-free-text-legs').value = ''; $('#manual-leg-description').value = ''; $('#manual-leg-line').value = ''; $('#manual-leg-odds').value = ''; });
  $('#manual-parlay-decision-source').addEventListener('change', syncDecisionContext);
  document.addEventListener('click', event => {
    const closeButton = event.target.closest('[data-close-manual-parlay]'); if (closeButton) modal.hidden = true;
    const modeButton = event.target.closest('[data-leg-mode]'); if (modeButton) setLegMode(modeButton.dataset.legMode);
    const legEditButton = event.target.closest('[data-edit-manual-leg]'); if (legEditButton) { editDraftLeg(Number(legEditButton.dataset.editManualLeg)); return; }
    const removeButton = event.target.closest('[data-remove-manual-leg]'); if (removeButton) { const index = Number(removeButton.dataset.removeManualLeg); draftLegs.splice(index, 1); if (editingLegIndex === index) stopLegEdit(); else if (editingLegIndex !== null && editingLegIndex > index) editingLegIndex -= 1; renderDraftLegs(); }
    const editButton = event.target.closest('[data-manual-parlay-edit]'); if (!editButton) return;
    const parlay = (window.proplensTrackedParlays || []).find(item => item.id === editButton.dataset.manualParlayEdit); if (parlay) openForEdit(parlay);
  });
  modal.addEventListener('click', event => { if (event.target === modal) modal.hidden = true; });
  $('#btn-add-guided-leg').addEventListener('click', addGuidedLeg); $('#btn-add-free-text-legs').addEventListener('click', addFreeTextLegs);
  legCategory.addEventListener('change', () => { renderLegMarkets(); syncAnytimeTouchdownLeg(); }); legMarket.addEventListener('change', syncAnytimeTouchdownLeg); $('#manual-leg-position').addEventListener('change', () => { applyDefaultLegMarket(); syncAnytimeTouchdownLeg(); });
  $('#manual-leg-player').addEventListener('input', () => { applyLegPlayerSuggestion(); clearTimeout(playerSearchTimer); playerSearchTimer = setTimeout(searchLegPlayers, 180); });
  ['#manual-parlay-odds', '#manual-parlay-stake', '#manual-parlay-boost', '#manual-parlay-return'].forEach(id => $(id).addEventListener('input', updateReturnPreview)); $('#manual-parlay-type').addEventListener('change', updateReturnPreview);
  status.addEventListener('change', updateSettlementVisibility); $('#manual-parlay-season').addEventListener('change', applyWeekSuggestion); $('#manual-parlay-week').addEventListener('change', rememberWeek);
  form.addEventListener('submit', async event => {
    event.preventDefault(); const button = $('#btn-save-manual-parlay'); button.disabled = true;
    try { const body = payload(); const url = editingId ? `/api/tracker/parlays/${editingId}/manual` : '/api/tracker/parlays/manual'; await api(url, { method: editingId ? 'PUT' : 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }); modal.hidden = true; clearScreenshotReview(); await window.proplensRefreshParlayTracker?.(); await window.proplensRefreshTracker?.(); toast(editingId ? 'Manual parlay updated.' : 'Manual parlay added to the tracker.'); }
    catch (error) { toast(error.message, true); } finally { button.disabled = false; }
  });
})();
