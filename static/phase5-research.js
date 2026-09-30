/* Phase 5: read-only research, with a human-reviewed availability lens. */
(() => {
  const $ = selector => document.querySelector(selector);
  const modal = $('#research-modal'), report = $('#research-report'), run = $('#btn-run-research');
  const drilldown = $('#research-drilldown-modal');
  const state = { market: '', rows: [], selected: null, report: null };
  const escapeHtml = value => String(value ?? '').replace(/[&<>'"]/g, char => ({ '&': '&amp;', '>': '&gt;', '<': '&lt;', "'": '&#39;', '"': '&quot;' }[char]));
  const number = value => Number(value || 0).toLocaleString();
  const signed = value => `${Number(value) >= 0 ? '+' : ''}${Number(value).toFixed(2)}`;
  const label = value => String(value || '').replaceAll('_', ' ');
  const annotationLabel = value => ({ unreviewed: 'Unreviewed', verified_in_game_injury: 'Verified in-game injury', non_injury_early_exit: 'Non-injury early exit', pre_game_inactive_or_scratch: 'Pre-game inactive / scratch', no_special_circumstance: 'No special circumstance' }[value] || 'Unreviewed');

  async function api(url, options = {}) {
    const response = await fetch(url, options);
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.detail || 'Could not run the research report.');
    return data;
  }
  function queryParams() {
    const query = new URLSearchParams();
    const season = $('#research-season').value.trim(), week = $('#research-week').value.trim();
    if (season) query.set('season', season);
    if (week) query.set('through_week', week);
    return query;
  }
  function render(data) {
    const coverage = data.coverage || {}, exclusions = Object.entries(coverage.excluded || {});
    const summaryView = $('#research-summary-view').value;
    const adjusted = summaryView === 'availability_adjusted';
    const marketRows = adjusted ? (data.availability_adjusted?.markets || []) : (data.markets || []);
    const excludedInjuries = Number(data.availability_adjusted?.excluded_verified_in_game_injuries || 0);
    $('#research-summary-view-help').textContent = adjusted
      ? `Availability-adjusted excludes ${excludedInjuries} verified in-game injury ${excludedInjuries === 1 ? 'row' : 'rows'} from each market's accuracy metrics.`
      : 'All outcomes includes every matched player-game. Coverage cards always remain raw data-quality counts.';
    const coverageCards = `<section class="research-coverage"><div><span>Supported imports</span><strong>${number(coverage.supported_imported_rows)}</strong></div><div><span>Selected pre-kickoff</span><strong>${number(coverage.selected_pre_kickoff_rows)}</strong></div><div><span>Matched final stats</span><strong>${number(coverage.matched_rows)}</strong></div></section>`;
    const exclusionHtml = exclusions.length ? `<section class="research-exclusions"><strong>Excluded safely</strong>${exclusions.map(([reason, count]) => `<span>${escapeHtml(label(reason))}: ${number(count)}</span>`).join('')}</section>` : '';
    const metrics = marketRows.length ? `<section class="research-market-table"><div class="research-market-heading"><span>Market</span><span>N</span><span>Proj.</span><span>Actual</span><span>Bias</span><span>MAE</span><span>RMSE</span></div>${marketRows.map(item => `<button class="research-market-row" type="button" data-market="${escapeHtml(item.market)}" title="Open player-level detail"><strong>${escapeHtml(item.label)}</strong><span>${item.sample_size}</span><span>${item.average_projection.toFixed(2)}</span><span>${item.average_actual.toFixed(2)}</span><span class="${item.bias_actual_minus_projection >= 0 ? 'positive' : 'negative'}">${signed(item.bias_actual_minus_projection)}</span><span>${item.mae.toFixed(2)}</span><span>${item.rmse.toFixed(2)}</span></button>`).join('')}</section>` : '<p class="field-help">No safely matched final statistics are available in this view yet.</p>';
    const errorExamples = adjusted ? (data.largest_errors || []).filter(item => !item.availability_adjusted_excluded) : (data.largest_errors || []);
    const largest = errorExamples.length ? `<section class="research-largest"><strong>Largest absolute errors — examples only</strong>${errorExamples.slice(0, 5).map(item => `<button type="button" data-market="${escapeHtml(item.market)}"><span>${escapeHtml(item.player_name)} · ${escapeHtml(label(item.market))}</span><span>${item.projection_mean.toFixed(1)} projected · ${item.actual_stat.toFixed(1)} actual · ${signed(item.error)}</span></button>`).join('')}</section>` : '';
    report.innerHTML = `${coverageCards}<p class="research-note">${escapeHtml(data.message || 'Descriptive only.')}</p>${exclusionHtml}<button type="button" class="research-review-button" id="btn-review-unmatched">Review unmatched rows</button>${metrics}${largest}`;
  }
  async function load() {
    run.disabled = true; run.textContent = 'Running…'; report.innerHTML = '<p class="field-help">Matching saved snapshots to the NFL schedule and final stats…</p>';
    try { state.report = await api(`/api/research/mean-accuracy?${queryParams().toString()}`); render(state.report); }
    catch (error) { report.innerHTML = `<p class="field-help">${escapeHtml(error.message)}</p>`; }
    finally { run.disabled = false; run.textContent = 'Run report'; }
  }
  function metricText(rows) {
    if (!rows.length) return 'No rows.';
    const errors = rows.map(row => Number(row.error));
    const bias = errors.reduce((sum, value) => sum + value, 0) / errors.length;
    const mae = rows.reduce((sum, row) => sum + Number(row.absolute_error), 0) / rows.length;
    const rmse = Math.sqrt(errors.reduce((sum, value) => sum + value * value, 0) / errors.length);
    return `${rows.length} rows · bias ${signed(bias)} · MAE ${mae.toFixed(2)} · RMSE ${rmse.toFixed(2)}`;
  }
  function baseFilteredRows() {
    const player = $('#research-drilldown-player').value.trim().toLowerCase();
    const team = $('#research-drilldown-team').value, week = $('#research-drilldown-week').value;
    return state.rows.filter(row => (!player || row.player_name.toLowerCase().includes(player)) && (!team || row.team === team) && (!week || String(row.week) === week));
  }
  function renderDrilldown() {
    const allRows = baseFilteredRows();
    const visible = $('#research-drilldown-view').value === 'availability_adjusted' ? allRows.filter(row => !row.availability_adjusted_excluded) : [...allRows];
    const sort = $('#research-drilldown-sort').value;
    visible.sort((left, right) => {
      if (sort === 'player_name') return left.player_name.localeCompare(right.player_name);
      if (sort === 'week') return Number(left.week) - Number(right.week) || right.absolute_error - left.absolute_error;
      return Number(right[sort]) - Number(left[sort]);
    });
    const injuryCount = allRows.filter(row => row.availability_adjusted_excluded).length;
    $('#research-drilldown-summary').innerHTML = `<span><strong>All outcomes</strong>${escapeHtml(metricText(allRows))}</span><span><strong>Availability-adjusted</strong>Excludes ${injuryCount} verified in-game injury ${injuryCount === 1 ? 'row' : 'rows'} · ${escapeHtml(metricText(allRows.filter(row => !row.availability_adjusted_excluded)))}</span>`;
    $('#research-drilldown-table').innerHTML = visible.length ? `<div class="research-detail-heading"><span>Player / matchup</span><span>Week</span><span>Snapshot</span><span>Projected</span><span>Actual</span><span>Error</span><span>Review</span></div>${visible.map(row => `<div class="research-detail-row"><strong>${escapeHtml(row.player_name)}<small>${escapeHtml(row.team)} vs ${escapeHtml(row.opponent)} · ${escapeHtml(row.position || '—')}</small></strong><span>${row.week}</span><span title="${escapeHtml(row.snapshot_imported_at)}">${escapeHtml(row.snapshot_label)}</span><span>${Number(row.projection_mean).toFixed(1)}</span><span>${Number(row.actual_stat).toFixed(1)}</span><span class="${row.error >= 0 ? 'positive' : 'negative'}">${signed(row.error)}</span><button type="button" class="research-review-button" data-record-id="${row.record_id}">${escapeHtml(annotationLabel(row.availability_classification))}</button></div>`).join('')}` : '<p class="field-help">No rows match these filters.</p>';
  }
  function selectForReview(recordId) {
    state.selected = state.rows.find(row => row.record_id === recordId) || null;
    if (!state.selected) return;
    $('#research-review-panel').hidden = false;
    $('#research-review-player').textContent = `${state.selected.player_name} · ${label(state.selected.market)}`;
    $('#research-review-values').textContent = `${state.selected.team} vs ${state.selected.opponent} · ${state.selected.projection_mean.toFixed(1)} projected · ${state.selected.actual_stat.toFixed(1)} actual`;
    $('#research-review-classification').value = state.selected.availability_classification;
    $('#research-review-note').value = state.selected.availability_note || '';
    $('#research-review-panel').scrollIntoView({ block: 'nearest' });
  }
  async function openDrilldown(market) {
    state.market = market; state.selected = null;
    $('#research-review-panel').hidden = true;
    $('#research-drilldown-title').textContent = `${label(market)} — player detail`;
    $('#research-drilldown-intro').textContent = 'Each row uses the latest saved projection before kickoff. Review only confirmed special circumstances; this never rewrites original data.';
    $('#research-drilldown-table').innerHTML = '<p class="field-help">Loading matched player rows…</p>';
    drilldown.hidden = false;
    try {
      const query = queryParams(); query.set('market', market);
      const data = await api(`/api/research/mean-accuracy/rows?${query.toString()}`);
      state.rows = data.records || [];
      const teams = [...new Set(state.rows.map(row => row.team).filter(Boolean))].sort();
      const weeks = [...new Set(state.rows.map(row => row.week))].sort((a, b) => a - b);
      $('#research-drilldown-team').innerHTML = '<option value="">All teams</option>' + teams.map(team => `<option value="${escapeHtml(team)}">${escapeHtml(team)}</option>`).join('');
      $('#research-drilldown-week').innerHTML = '<option value="">All weeks</option>' + weeks.map(item => `<option value="${item}">Week ${item}</option>`).join('');
      renderDrilldown();
    } catch (error) { $('#research-drilldown-table').innerHTML = `<p class="field-help">${escapeHtml(error.message)}</p>`; }
  }
  async function saveReview() {
    if (!state.selected) return;
    const button = $('#btn-save-research-review');
    button.disabled = true; button.textContent = 'Saving…';
    try {
      const saved = await api('/api/research/mean-accuracy/annotations', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ record_id: state.selected.record_id, classification: $('#research-review-classification').value, note: $('#research-review-note').value }) });
      state.selected.availability_classification = saved.classification;
      state.selected.availability_note = saved.note || '';
      state.selected.availability_adjusted_excluded = saved.classification === 'verified_in_game_injury';
      $('#research-review-panel').hidden = true;
      renderDrilldown();
    } catch (error) { $('#research-review-panel .field-help').textContent = error.message; }
    finally { button.disabled = false; button.textContent = 'Save review'; }
  }

  $('#btn-open-research').addEventListener('click', () => { modal.hidden = false; });
  run.addEventListener('click', load);
  $('#research-summary-view').addEventListener('change', () => { if (state.report) render(state.report); });
  report.addEventListener('click', event => { const button = event.target.closest('[data-market]'); if (button) openDrilldown(button.dataset.market); });
  $('#research-drilldown-table').addEventListener('click', event => { const button = event.target.closest('[data-record-id]'); if (button) selectForReview(button.dataset.recordId); });
  ['#research-drilldown-player', '#research-drilldown-team', '#research-drilldown-week', '#research-drilldown-view', '#research-drilldown-sort'].forEach(selector => {
    $(selector).addEventListener('input', renderDrilldown);
    $(selector).addEventListener('change', renderDrilldown);
  });
  $('#btn-save-research-review').addEventListener('click', saveReview);
})();
