/* Phase 4A: tracking-only manual straight-bet entry. */
(() => {
  const $ = selector => document.querySelector(selector);
  const modal = $('#manual-bet-modal');
  const form = $('#manual-bet-form');
  const category = $('#manual-category');
  const market = $('#manual-market');
  const status = $('#manual-status');
  const settlementField = $('#manual-settlement-field');
  const playerFields = [...document.querySelectorAll('.manual-player-field')];
  const selectionFields = [...document.querySelectorAll('.manual-selection-field')];
  const weekHelp = $('#manual-week-help');
  const weekOneStarts = { 2026: [2026, 8, 9] };
  let editingId = null;
  let playerMatches = [];
  let searchTimer = null;

  const markets = {
    player_prop: [
      ['passing_yards', 'Passing yards'], ['passing_tds', 'Passing TDs'],
      ['passing_interceptions', 'Passing interceptions'], ['rushing_yards', 'Rushing yards'],
      ['rushing_receiving_yards', 'Rushing + receiving yards'],
      ['receiving_yards', 'Receiving yards'], ['receptions', 'Receptions'],
      ['anytime_td', 'Anytime TD'], ['tackles_assists', 'Tackles + assists'],
      ['solo_tackles', 'Solo tackles'], ['sacks', 'Sacks'],
      ['defensive_interceptions', 'Defensive interceptions'], ['passes_defended', 'Passes defended'],
      ['defensive_td', 'Defensive TD'], ['custom_player_prop', 'Other player prop'],
    ],
    game_bet: [
      ['moneyline', 'Moneyline'], ['spread', 'Spread'], ['game_total', 'Game total'],
      ['team_total', 'Team total'], ['custom_game_bet', 'Other game bet'],
    ],
    custom: [['custom', 'Other / custom bet']],
  };

  const value = id => $(id).value.trim();
  const numberOrNull = id => value(id) === '' ? null : Number(value(id));
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
      const detail = Array.isArray(data.detail) ? data.detail.map(item => item.msg).join(' ') : data.detail;
      throw new Error(detail || 'Something went wrong.');
    }
    return data;
  }

  function renderMarkets(selected = '') {
    market.innerHTML = markets[category.value].map(([key, label]) => `<option value="${key}">${label}</option>`).join('');
    if (selected && [...market.options].some(option => option.value === selected)) market.value = selected;
    playerFields.forEach(field => field.hidden = category.value !== 'player_prop');
    selectionFields.forEach(field => field.hidden = category.value === 'custom');
    if (!selected) $('#manual-side').value = category.value === 'game_bet' ? 'Home' : category.value === 'custom' ? 'Other' : 'Over';
  }

  function applyDefaultMarketForPosition() {
    const defaults = { QB: 'passing_yards', RB: 'rushing_yards', WR: 'receiving_yards', TE: 'receiving_yards' };
    const defaultMarket = defaults[$('#manual-position').value];
    if (defaultMarket && [...market.options].some(option => option.value === defaultMarket)) market.value = defaultMarket;
  }

  function suggestedWeekForSeason(season) {
    const startParts = weekOneStarts[season];
    if (!startParts) return null;
    const start = new Date(...startParts);
    const today = new Date();
    today.setHours(0, 0, 0, 0);
    const daysFromWeekOneStart = Math.floor((today - start) / 86400000);
    const week = Math.floor((daysFromWeekOneStart + 1) / 7) + 1;
    if (week < 1 || week > 18) return null;
    return week;
  }

  function applyWeekSuggestion() {
    const season = Number(value('#manual-season'));
    const storedWeek = Number(sessionStorage.getItem(`proplens-manual-week-${season}`));
    const suggestedWeek = Number.isInteger(storedWeek) && storedWeek >= 1 && storedWeek <= 25 ? storedWeek : suggestedWeekForSeason(season);
    $('#manual-week').value = suggestedWeek || '';
    if (storedWeek) weekHelp.textContent = `Using Week ${storedWeek}, your last choice this session.`;
    else if (suggestedWeek) weekHelp.textContent = `Suggested Week ${suggestedWeek} from today's NFL calendar. You can change it.`;
    else weekHelp.textContent = 'Choose the week manually for this season.';
  }

  function rememberManualWeek() {
    const season = Number(value('#manual-season'));
    const week = Number(value('#manual-week'));
    if (!Number.isInteger(season) || !Number.isInteger(week) || week < 1 || week > 25) return;
    sessionStorage.setItem(`proplens-manual-week-${season}`, String(week));
    weekHelp.textContent = `Week ${week} will be used for new manual bets this session.`;
  }

  function updateSettlementVisibility() {
    settlementField.hidden = status.value !== 'cashed_out';
  }

  function suggestedDescription() {
    const marketText = market.options[market.selectedIndex]?.text || 'Bet';
    const side = value('#manual-side');
    const line = value('#manual-line');
    if (category.value === 'player_prop') return value('#manual-player');
    if (category.value === 'game_bet') return [value('#manual-team'), value('#manual-opponent') ? `vs ${value('#manual-opponent')}` : ''].filter(Boolean).join(' ') || 'Game bet';
    return '';
  }

  function resetForm() {
    form.reset();
    category.value = 'player_prop';
    status.value = 'pending';
    editingId = null;
    renderMarkets();
    updateSettlementVisibility();
    applyWeekSuggestion();
    $('#manual-bet-title').textContent = 'Track a manual bet';
    $('#btn-save-manual-bet').textContent = 'Save manual bet';
  }

  function payload() {
    const description = value('#manual-description') || suggestedDescription();
    const season = numberOrNull('#manual-season');
    const week = numberOrNull('#manual-week');
    const settlement = numberOrNull('#manual-settlement');
    if (!description) throw new Error('Enter a short description for this custom bet.');
    if ((season === null) !== (week === null)) throw new Error('Enter both season and NFL week, or leave both blank.');
    if (status.value === 'cashed_out' && settlement === null) throw new Error('Enter the actual cash-out amount.');
    return {
      category: category.value,
      description,
      player_name: category.value === 'player_prop' ? value('#manual-player') || null : null,
      position: category.value === 'player_prop' ? value('#manual-position') || null : null,
      team: value('#manual-team') || null,
      opponent: value('#manual-opponent') || null,
      market: market.value,
      side_label: category.value === 'custom' ? null : value('#manual-side') || null,
      line: category.value === 'custom' ? null : numberOrNull('#manual-line'),
      decimal_odds: Number(value('#manual-odds')),
      stake: Number(value('#manual-stake')),
      bet_type: value('#manual-type'),
      season,
      week,
      status: status.value,
      settlement_amount: settlement,
    };
  }

  async function searchPlayers() {
    const query = value('#manual-player');
    try {
      const data = await api(`/api/evaluator/players?q=${encodeURIComponent(query)}&limit=20`);
      playerMatches = data.players || [];
      $('#manual-player-options').innerHTML = playerMatches.map(player => `<option value="${player.player_name}">${player.team} · ${player.position}</option>`).join('');
      applyPlayerSuggestion();
    } catch (_) {
      playerMatches = [];
    }
  }

  function applyPlayerSuggestion() {
    const typed = value('#manual-player').toLowerCase();
    const match = playerMatches.find(player => player.player_name.toLowerCase() === typed);
    if (!match) return;
    $('#manual-team').value = match.team || '';
    $('#manual-opponent').value = match.opponent || '';
    $('#manual-position').value = match.position || '';
    applyDefaultMarketForPosition();
  }

  function openForEdit(bet) {
    editingId = bet.id;
    category.value = bet.category || 'custom';
    renderMarkets(bet.market);
    $('#manual-description').value = bet.description || '';
    $('#manual-player').value = bet.category === 'player_prop' ? bet.player_name || '' : '';
    $('#manual-position').value = bet.position || bet.result_identity?.position || '';
    $('#manual-side').value = bet.side_label || 'Other';
    $('#manual-line').value = bet.line ?? '';
    $('#manual-team').value = bet.team || '';
    $('#manual-opponent').value = bet.opponent || '';
    $('#manual-season').value = bet.result_identity?.season ?? '';
    $('#manual-week').value = bet.result_identity?.week ?? '';
    weekHelp.textContent = bet.result_identity?.week ? `Saved Week ${bet.result_identity.week}. Editing does not change it automatically.` : 'No NFL week was saved for this record.';
    $('#manual-odds').value = bet.decimal_odds;
    $('#manual-stake').value = bet.stake;
    $('#manual-type').value = bet.bet_type;
    status.value = bet.status;
    $('#manual-settlement').value = bet.settlement_amount ?? '';
    updateSettlementVisibility();
    $('#manual-bet-title').textContent = 'Edit manual bet';
    $('#btn-save-manual-bet').textContent = 'Save changes';
    modal.hidden = false;
  }

  $('#btn-manual-bet').addEventListener('click', () => { resetForm(); modal.hidden = false; searchPlayers(); });
  category.addEventListener('change', () => renderMarkets());
  $('#manual-position').addEventListener('change', applyDefaultMarketForPosition);
  $('#manual-season').addEventListener('change', applyWeekSuggestion);
  $('#manual-week').addEventListener('change', rememberManualWeek);
  status.addEventListener('change', updateSettlementVisibility);
  $('#manual-player').addEventListener('input', () => {
    applyPlayerSuggestion();
    clearTimeout(searchTimer);
    searchTimer = setTimeout(searchPlayers, 180);
  });
  document.addEventListener('click', event => {
    const button = event.target.closest('[data-edit-manual]');
    if (!button) return;
    const bet = (window.proplensTrackedBets || []).find(item => item.id === button.dataset.editManual);
    if (bet) openForEdit(bet);
  });
  form.addEventListener('submit', async event => {
    event.preventDefault();
    const button = $('#btn-save-manual-bet');
    button.disabled = true;
    try {
      const body = payload();
      const url = editingId ? `/api/tracker/bets/${editingId}/manual` : '/api/tracker/bets/manual';
      await api(url, { method: editingId ? 'PUT' : 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
      modal.hidden = true;
      await window.proplensRefreshTracker?.();
      toast(editingId ? 'Manual bet updated.' : 'Manual bet added to the tracker.');
    } catch (error) {
      toast(error.message, true);
    } finally {
      button.disabled = false;
    }
  });
})();
