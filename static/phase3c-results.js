/* Phase 3C.1A: preview final stats for eligible tracked parlay legs. */
(() => {
  const $ = selector => document.querySelector(selector);
  const escapeHtml = value => String(value ?? '').replace(/[&<>'"]/g, character => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;' }[character]));
  const modal = document.createElement('div');
  modal.className = 'modal-backdrop';
  modal.id = 'parlay-result-preview-modal';
  modal.hidden = true;
  modal.innerHTML = `<section class="modal-card parlay-result-preview-card" role="dialog" aria-modal="true" aria-labelledby="parlay-result-preview-title"><button class="modal-close" type="button" aria-label="Close">×</button><p class="eyebrow">PHASE 3C.1A · PREVIEW ONLY</p><h2 id="parlay-result-preview-title">Parlay result suggestions</h2><p id="parlay-result-preview-summary">Checking pending parlays…</p><p class="parlay-result-preview-note">Nothing here changes your tracker. Confirm every result against Bet365, then use the normal settlement buttons.</p><div id="parlay-result-preview-list" class="parlay-result-preview-list"></div></section>`;
  document.body.append(modal);

  const options = $('#parlay-tracker-modal .parlay-tracker-options');
  options.insertAdjacentHTML('afterbegin', '<button type="button" class="parlay-result-check" id="btn-check-parlay-results">Check parlay results</button>');
  const checkButton = $('#btn-check-parlay-results');
  const summary = $('#parlay-result-preview-summary');
  const list = $('#parlay-result-preview-list');

  const statusLabel = status => ({ proposal: 'Ready to review', waiting: 'Waiting for stats', push_review: 'Push review', needs_review: 'Needs review', manual_required: 'Manual settlement required', stats_unavailable: 'Waiting for stats', game_not_final: 'Waiting for stats', source_error: 'Source unavailable', player_review: 'Needs review', unsupported_market: 'Manual settlement required' }[status] || 'Review');
  const legName = leg => [leg.player_name, leg.market?.replaceAll('_', ' '), leg.line ?? ''].filter(value => value !== '').join(' · ');
  const actual = leg => leg.actual_stat === undefined ? '' : `<small>Actual: ${Number(leg.actual_stat).toFixed(1)} ${escapeHtml(leg.stat_label || '')}</small>`;

  function parlayMarkup(parlay) {
    const result = parlay.proposed_result ? `Suggest ${parlay.proposed_result[0].toUpperCase()}${parlay.proposed_result.slice(1)}` : statusLabel(parlay.status);
    const legs = parlay.legs.map(leg => `<article class="parlay-result-leg ${escapeHtml(leg.status)}"><div><strong>${escapeHtml(legName(leg))}</strong>${actual(leg)}<small>${escapeHtml(leg.message)}</small></div><span>${leg.proposed_result ? leg.proposed_result[0].toUpperCase() + leg.proposed_result.slice(1) : statusLabel(leg.status)}</span></article>`).join('');
    return `<section class="parlay-result-preview-item ${escapeHtml(parlay.status)}"><div class="parlay-result-preview-heading"><div><strong>${escapeHtml(parlay.description)}</strong><small>${escapeHtml(parlay.message)}</small></div><span>${result}</span></div>${legs}</section>`;
  }

  async function checkResults() {
    checkButton.disabled = true;
    checkButton.textContent = 'Checking…';
    modal.hidden = false;
    summary.textContent = 'Checking eligible pending parlay legs…';
    list.innerHTML = '';
    try {
      const response = await fetch('/api/tracker/parlays/results/preview', { method: 'POST' });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(data.detail || 'Could not check parlay results.');
      summary.textContent = `${data.checked_pending} pending parlay${data.checked_pending === 1 ? '' : 's'} checked. Suggestions are preview only.`;
      list.innerHTML = data.parlays.length ? data.parlays.map(parlayMarkup).join('') : '<p class="field-help">No pending parlays to check.</p>';
    } catch (error) {
      summary.textContent = error.message;
      list.innerHTML = '<p class="field-help">Your tracked parlays were not changed.</p>';
    } finally {
      checkButton.disabled = false;
      checkButton.textContent = 'Check parlay results';
    }
  }

  checkButton.addEventListener('click', checkResults);
  modal.querySelector('.modal-close').addEventListener('click', () => { modal.hidden = true; });
  modal.addEventListener('click', event => { if (event.target === modal) modal.hidden = true; });
})();
