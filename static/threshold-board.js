/* Projection-only threshold watchlist. It never reads or stores bookmaker odds. */
(() => {
  const actions = document.querySelector('.topbar-actions');
  if (!actions) return;
  const open = document.createElement('button');
  open.type = 'button'; open.className = 'text-button'; open.textContent = 'Threshold board';
  actions.insertBefore(open, actions.querySelector('#btn-open-parlay'));

  const modal = document.createElement('div');
  modal.className = 'modal-backdrop'; modal.hidden = true;
  modal.innerHTML = `<section class="modal-card threshold-board-card" role="dialog" aria-modal="true" aria-labelledby="threshold-board-title"><button class="modal-close" aria-label="Close">×</button><p class="eyebrow">PROJECTION WATCHLIST</p><h2 id="threshold-board-title">Positive-line thresholds</h2><p>See the highest Over line and lowest Under line that the loaded projection model rates positive at your assumed price. This is a shortlist, not a live Bet365 odds feed.</p><div class="threshold-fields"><label>Game<select class="threshold-game"></select></label><label>Market<select class="threshold-market"><option value="receiving_yards">Receiving yards</option><option value="receptions">Receptions</option><option value="rushing_yards">Rushing yards</option><option value="passing_yards">Passing yards</option><option value="passing_tds">Passing TDs</option><option value="passing_interceptions">Interceptions</option></select></label><label>Assumed decimal odds<input class="threshold-odds" inputmode="decimal" value="1.86"></label></div><button class="secondary-button threshold-load" type="button">Build watchlist</button><p class="field-help threshold-status"></p><section class="threshold-results" hidden><p class="threshold-reading">At this assumed price: an Over is positive at or below the <b>Max Over</b> line; an Under is positive at or above the <b>Min Under</b> line. The distribution can be asymmetric, so do not use the projection mean alone as a rule.</p><div class="threshold-table-wrap"><table><thead><tr><th>Player</th><th>Projection</th><th>Max Over</th><th>Min Under</th></tr></thead><tbody></tbody></table></div><p class="field-help">Choose Evaluate beside a threshold to open that player in the normal evaluator. The assumed line and price are prefilled; replace them with the exact live Bet365 quote before calculating.</p></section></section>`;
  document.body.append(modal);

  const style = document.createElement('style');
  style.textContent = `.threshold-board-card{width:min(900px,calc(100vw - 28px));max-height:calc(100vh - 28px);overflow:auto}.threshold-fields{display:grid;grid-template-columns:1.4fr 1fr .7fr;gap:11px}.threshold-fields label{margin-top:10px!important}.threshold-load{margin-top:16px!important}.threshold-status{min-height:18px}.threshold-status.error{color:#ff8d9b}.threshold-results{margin-top:14px}.threshold-reading{margin:0 0 10px!important;padding:10px;border-left:2px solid #8bc5ff;background:rgba(139,197,255,.06);font-size:11px!important}.threshold-reading b{color:#e6eefc}.threshold-table-wrap{max-height:48vh;overflow:auto;border:1px solid #293652;border-radius:9px}.threshold-table-wrap table{width:100%;min-width:650px;border-collapse:collapse}.threshold-table-wrap th,.threshold-table-wrap td{padding:10px;border-bottom:1px solid #293652;text-align:left;font-size:12px}.threshold-table-wrap th{position:sticky;top:0;background:#182238;color:#98a6bf;font:500 10px var(--mono);letter-spacing:.05em;text-transform:uppercase}.threshold-player strong,.threshold-player small{display:block}.threshold-player small{margin-top:3px;color:var(--muted);font-size:10px}.threshold-line{font:600 13px var(--mono)}.threshold-line.over{color:#75f0b4}.threshold-line.under{color:#8bc5ff}.threshold-evaluate{display:block;margin-top:6px;padding:4px 6px;border:1px solid currentColor;border-radius:5px;background:transparent;color:inherit;font:500 10px var(--mono);white-space:nowrap}.threshold-evaluate:hover{background:rgba(255,255,255,.07)}@media(max-width:620px){.threshold-fields{grid-template-columns:1fr}.threshold-table-wrap{max-height:42vh}}`;
  document.head.append(style);

  const game = modal.querySelector('.threshold-game'), market = modal.querySelector('.threshold-market'), odds = modal.querySelector('.threshold-odds'), load = modal.querySelector('.threshold-load'), status = modal.querySelector('.threshold-status'), results = modal.querySelector('.threshold-results'), body = modal.querySelector('tbody');
  const esc = value => String(value ?? '').replace(/[&<>'"]/g, char => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;' }[char]));
  async function request(url) { const response = await fetch(url); const data = await response.json().catch(() => ({})); if (!response.ok) throw new Error(data.detail || 'Could not build the watchlist.'); return data; }
  async function loadGames() {
    game.innerHTML = '<option>Loading games…</option>'; game.disabled = true;
    const data = await request('/api/evaluator/browse?sort_market=receiving_yards&limit=1');
    game.innerHTML = data.games.length ? data.games.map(item => `<option value="${esc(item.key)}">${esc(item.label)}</option>`).join('') : '<option value="">No game context in the active projections</option>';
    game.disabled = !data.games.length;
  }
  async function build() {
    const price = Number(odds.value);
    if (!Number.isFinite(price) || price <= 1) { status.textContent = 'Enter decimal odds above 1.00, for example 1.86.'; status.classList.add('error'); return; }
    load.disabled = true; load.textContent = 'Building watchlist…'; status.classList.remove('error'); status.textContent = 'Using the loaded projections only…'; results.hidden = true;
    try {
      const data = await request(`/api/evaluator/threshold-board?game=${encodeURIComponent(game.value)}&market=${encodeURIComponent(market.value)}&odds=${encodeURIComponent(price)}`);
      body.innerHTML = data.rows.map(row => { const player = esc(row.player_name), team = esc(row.team), over = row.over_max_positive_line, under = row.under_min_positive_line; const action = (side, line) => line === null || line === undefined ? '—' : `${line}<button type="button" class="threshold-evaluate" data-player="${player}" data-team="${team}" data-market="${esc(data.market)}" data-side="${side}" data-line="${line}" data-odds="${data.assumed_decimal_odds}">Evaluate ${side === 'over' ? 'Over' : 'Under'}</button>`; return `<tr><td class="threshold-player"><strong>${player}</strong><small>${team}${row.opponent ? ` vs ${esc(row.opponent)}` : ''} · ${esc(row.position)}</small></td><td class="threshold-line">${Number(row.projection_mean).toFixed(1)}</td><td class="threshold-line over">${action('over', over)}</td><td class="threshold-line under">${action('under', under)}</td></tr>`; }).join('') || '<tr><td colspan="4">No matching projections were found for this game and market.</td></tr>';
      status.textContent = `${data.rows.length} projected player${data.rows.length === 1 ? '' : 's'} · assumed price ${Number(data.assumed_decimal_odds).toFixed(2)}. ${data.notice}`;
      results.hidden = false;
    } catch (error) { status.textContent = error.message; status.classList.add('error'); }
    finally { load.disabled = false; load.textContent = 'Build watchlist'; }
  }
  // Refresh the slate whenever the board opens, so a newly imported active
  // projection set immediately supplies its own week and games.
  open.addEventListener('click', async () => { modal.hidden = false; results.hidden = true; status.textContent = ''; try { await loadGames(); } catch (error) { status.textContent = error.message; status.classList.add('error'); } });
  modal.querySelector('.modal-close').addEventListener('click', () => { modal.hidden = true; });
  modal.addEventListener('click', event => { if (event.target === modal) modal.hidden = true; });
  load.addEventListener('click', build);
  body.addEventListener('click', async event => {
    const button = event.target.closest('.threshold-evaluate'); if (!button) return;
    button.disabled = true;
    try {
      const data = await request(`/api/evaluator/players?q=${encodeURIComponent(button.dataset.player)}&limit=20`);
      const player = data.players.find(item => item.player_name.toLowerCase() === button.dataset.player.toLowerCase() && item.team.toUpperCase() === button.dataset.team.toUpperCase() && item.markets.includes(button.dataset.market));
      if (!player) throw new Error('This player could not be matched safely in the active projections.');
      window.proplensStartEvaluation(player, { market: button.dataset.market, side: button.dataset.side, line: Number(button.dataset.line), odds: Number(button.dataset.odds) });
      modal.hidden = true;
    } catch (error) { status.textContent = error.message; status.classList.add('error'); button.disabled = false; }
  });
})();
