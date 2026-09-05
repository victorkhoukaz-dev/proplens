(() => {
  const modal = document.querySelector('#projection-browser-modal');
  const openButton = document.querySelector('#btn-open-projection-browser');
  const position = document.querySelector('#projection-browser-position');
  const game = document.querySelector('#projection-browser-game');
  const market = document.querySelector('#projection-browser-market');
  const context = document.querySelector('#projection-browser-context');
  const count = document.querySelector('#projection-browser-count');
  const list = document.querySelector('#projection-browser-list');
  const recentSection = document.querySelector('#recent-players');
  const recentButtons = document.querySelector('#recent-player-buttons');
  const closeButton = modal.querySelector('[data-close="projection-browser-modal"]');
  const recentStorageKey = 'proplens_recent_evaluated_players_v1';
  const preferredMarket = { QB: 'passing_yards', RB: 'rushing_yards', WR: 'receiving_yards', TE: 'receiving_yards' };
  const compactLabels = {
    passing_yards: 'Pass', passing_tds: 'Pass TD', rushing_yards: 'Rush',
    receiving_yards: 'Rec', receptions: 'Recs', anytime_td: 'TD',
  };
  let players = [];

  const escapeHtml = value => String(value ?? '').replace(/[&<>'"]/g, character => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;' }[character]));
  const displayValue = (key, value) => key === 'anytime_td' ? Number(value).toFixed(2) : Number(value).toFixed(1);

  function showToast(message, error = false) {
    const item = document.createElement('div');
    item.className = `toast${error ? ' error' : ''}`;
    item.textContent = message;
    document.querySelector('#toast-container').append(item);
    setTimeout(() => item.remove(), 4200);
  }

  function getRecent() {
    try {
      const saved = JSON.parse(localStorage.getItem(recentStorageKey) || '[]');
      return Array.isArray(saved) ? saved.slice(0, 8) : [];
    } catch {
      return [];
    }
  }

  function renderRecent() {
    const recent = getRecent();
    recentSection.hidden = !recent.length;
    recentButtons.innerHTML = recent.map((player, index) => `<button type="button" data-recent-player="${index}">${escapeHtml(player.player_name)}<small>${escapeHtml(player.team || '')}</small></button>`).join('');
  }

  function rememberEvaluation(player) {
    if (!player?.player_name) return;
    const recent = getRecent().filter(item => item.player_name.toLowerCase() !== player.player_name.toLowerCase() || item.team !== player.team);
    recent.unshift({ player_name: player.player_name, team: player.team || '' });
    try {
      localStorage.setItem(recentStorageKey, JSON.stringify(recent.slice(0, 8)));
    } catch {
      return;
    }
    renderRecent();
  }

  async function selectRecent(index) {
    const recent = getRecent()[index];
    if (!recent) return;
    try {
      const response = await fetch(`/api/evaluator/players?q=${encodeURIComponent(recent.player_name)}&limit=30`);
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(data.detail || 'Could not refresh that player.');
      const player = (data.players || []).find(item => item.player_name.toLowerCase() === recent.player_name.toLowerCase() && (!recent.team || item.team === recent.team));
      if (!player) throw new Error(`${recent.player_name} is not in the active projection set.`);
      window.proplensSelectPlayer(player);
    } catch (error) {
      showToast(error.message, true);
    }
  }

  function close() {
    modal.hidden = true;
  }

  function renderRows() {
    if (!players.length) {
      list.innerHTML = '<p class="projection-browser-empty">No players in the active projection set match those filters.</p>';
      return;
    }
    list.innerHTML = players.map((player, index) => {
      const values = Object.entries(player.projections || {})
        .filter(([key]) => compactLabels[key])
        .sort(([left], [right]) => (left === market.value ? -1 : right === market.value ? 1 : left.localeCompare(right)))
        .slice(0, 4)
        .map(([key, value]) => `<span class="projection-value${key === market.value ? ' featured' : ''}">${compactLabels[key]}<strong>${displayValue(key, value)}</strong></span>`)
        .join('');
      const matchup = player.opponent ? `${player.team} vs ${player.opponent}` : player.team;
      return `<button class="projection-row" type="button" data-projection-player="${index}"><span class="projection-player"><strong>${escapeHtml(player.player_name)}</strong><small>${escapeHtml(player.position)} · ${escapeHtml(matchup)}</small></span><span class="projection-values">${values}</span></button>`;
    }).join('');
  }

  async function load() {
    list.innerHTML = '<p class="field-help">Loading projections…</p>';
    try {
      const response = await fetch(`/api/evaluator/browse?position=${encodeURIComponent(position.value)}&game=${encodeURIComponent(game.value)}&sort_market=${encodeURIComponent(market.value)}&limit=30`);
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(data.detail || 'Could not load the active projection set.');
      const selectedPosition = position.value;
      const selectedGame = game.value;
      position.innerHTML = '<option value="all">All positions</option>' + data.positions.map(value => `<option value="${escapeHtml(value)}">${escapeHtml(value)}</option>`).join('');
      position.value = selectedPosition;
      game.innerHTML = '<option value="all">All games</option>' + data.games.map(item => `<option value="${escapeHtml(item.key)}">${escapeHtml(item.label)}</option>`).join('');
      game.value = selectedGame;
      players = data.players || [];
      const source = data.projection_context;
      context.textContent = source ? `Active set: ${source.label}` : 'Active imported projection set';
      count.textContent = `${players.length} shown`;
      renderRows();
    } catch (error) {
      players = [];
      count.textContent = '';
      list.innerHTML = `<p class="projection-browser-empty">${escapeHtml(error.message)}</p>`;
    }
  }

  openButton.addEventListener('click', async () => {
    modal.hidden = false;
    await load();
  });
  closeButton.addEventListener('click', close);
  modal.addEventListener('click', event => { if (event.target === modal) close(); });
  position.addEventListener('change', async () => {
    game.value = 'all';
    if (preferredMarket[position.value]) market.value = preferredMarket[position.value];
    await load();
  });
  game.addEventListener('change', async () => {
    position.value = 'all';
    await load();
  });
  market.addEventListener('change', load);
  list.addEventListener('click', event => {
    const row = event.target.closest('[data-projection-player]');
    if (!row) return;
    const player = players[Number(row.dataset.projectionPlayer)];
    if (!player || typeof window.proplensSelectPlayer !== 'function') return;
    window.proplensSelectPlayer(player);
    close();
  });
  recentButtons.addEventListener('click', event => {
    const button = event.target.closest('[data-recent-player]');
    if (button) selectRecent(Number(button.dataset.recentPlayer));
  });
  window.addEventListener('proplens:evaluation-complete', event => rememberEvaluation(event.detail));
  renderRecent();
})();
