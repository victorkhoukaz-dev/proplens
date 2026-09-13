/* Phase 5.0: descriptive projection mean accuracy, with no live model mutation. */
(() => {
  const $ = selector => document.querySelector(selector);
  const modal = $('#research-modal'), report = $('#research-report'), run = $('#btn-run-research');
  const escapeHtml = value => String(value ?? '').replace(/[&<>'"]/g, char => ({ '&': '&amp;', '>': '&gt;', '<': '&lt;', "'": '&#39;', '"': '&quot;' }[char]));
  const number = value => Number(value || 0).toLocaleString();
  const signed = value => `${Number(value) >= 0 ? '+' : ''}${Number(value).toFixed(2)}`;

  async function api(url) {
    const response = await fetch(url);
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.detail || 'Could not run the research report.');
    return data;
  }
  function render(data) {
    const coverage = data.coverage || {}, exclusions = Object.entries(coverage.excluded || {});
    const coverageCards = `<section class="research-coverage"><div><span>Supported imports</span><strong>${number(coverage.supported_imported_rows)}</strong></div><div><span>Selected pre-kickoff</span><strong>${number(coverage.selected_pre_kickoff_rows)}</strong></div><div><span>Matched final stats</span><strong>${number(coverage.matched_rows)}</strong></div></section>`;
    const exclusionHtml = exclusions.length ? `<section class="research-exclusions"><strong>Excluded safely</strong>${exclusions.map(([reason, count]) => `<span>${escapeHtml(reason.replaceAll('_', ' '))}: ${number(count)}</span>`).join('')}</section>` : '';
    const metrics = data.markets?.length ? `<section class="research-market-table"><div class="research-market-heading"><span>Market</span><span>N</span><span>Proj.</span><span>Actual</span><span>Bias</span><span>MAE</span><span>RMSE</span></div>${data.markets.map(item => `<div><strong>${escapeHtml(item.label)}</strong><span>${item.sample_size}</span><span>${item.average_projection.toFixed(2)}</span><span>${item.average_actual.toFixed(2)}</span><span class="${item.bias_actual_minus_projection >= 0 ? 'positive' : 'negative'}">${signed(item.bias_actual_minus_projection)}</span><span>${item.mae.toFixed(2)}</span><span>${item.rmse.toFixed(2)}</span></div>`).join('')}</section>` : '<p class="field-help">No safely matched final statistics are available in this scope yet.</p>';
    const largest = data.largest_errors?.length ? `<section class="research-largest"><strong>Largest absolute errors — examples only</strong>${data.largest_errors.slice(0, 5).map(item => `<div><span>${escapeHtml(item.player_name)} · ${escapeHtml(item.market.replaceAll('_', ' '))}</span><span>${item.projection_mean.toFixed(1)} projected · ${item.actual_stat.toFixed(1)} actual · ${signed(item.error)}</span></div>`).join('')}</section>` : '';
    report.innerHTML = `${coverageCards}<p class="research-note">${escapeHtml(data.message || 'Descriptive only.')}</p>${exclusionHtml}${metrics}${largest}`;
  }
  async function load() {
    const params = new URLSearchParams();
    const season = $('#research-season').value.trim(), week = $('#research-week').value.trim();
    if (season) params.set('season', season);
    if (week) params.set('through_week', week);
    run.disabled = true; run.textContent = 'Running…'; report.innerHTML = '<p class="field-help">Matching saved snapshots to the NFL schedule and final stats…</p>';
    try { render(await api(`/api/research/mean-accuracy?${params.toString()}`)); }
    catch (error) { report.innerHTML = `<p class="field-help">${escapeHtml(error.message)}</p>`; }
    finally { run.disabled = false; run.textContent = 'Run report'; }
  }
  $('#btn-open-research').addEventListener('click', () => { modal.hidden = false; });
  run.addEventListener('click', load);
})();
