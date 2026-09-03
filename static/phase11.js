/* Phase 1.1: projection snapshots, import context, and matchup clarity. */
(() => {
  const libraryButton = document.querySelector('#btn-open-library');
  const libraryModal = document.querySelector('#library-modal');
  const libraryList = document.querySelector('#library-list');
  const selectedPlayer = document.querySelector('#player-selected');
  const resultContent = document.querySelector('#result-content');
  let activeSnapshot = null;
  let latestEvaluation = null;

  const escapeHtml = value => String(value ?? '').replace(/[&<>'"]/g, char => ({ '&':'&amp;', '<':'&lt;', '>':'&gt;', "'":'&#39;', '"':'&quot;' }[char]));
  const showMessage = (message, error = false) => {
    const item = document.createElement('div');
    item.className = `toast${error ? ' error' : ''}`;
    item.textContent = message;
    document.querySelector('#toast-container').append(item);
    setTimeout(() => item.remove(), 4200);
  };
  async function api(url, options) {
    const response = await fetch(url, options);
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.detail || 'Something went wrong.');
    return data;
  }
  function importMetadata() {
    return {
      season: Number(document.querySelector('#import-season').value),
      week: Number(document.querySelector('#import-week').value),
      label: document.querySelector('#import-label').value.trim(),
    };
  }
  function appendContext() {
    const text = selectedPlayer.textContent.trim();
    if (!activeSnapshot || !text || text.startsWith('Start by')) return;
    const existing = selectedPlayer.querySelector('.projection-context');
    if (existing?.dataset.snapshotId === activeSnapshot.id) return;
    existing?.remove();
    const context = document.createElement('small');
    context.className = 'projection-context';
    context.dataset.snapshotId = activeSnapshot.id;
    context.textContent = ` · NFL ${activeSnapshot.season} Week ${activeSnapshot.week} · ${activeSnapshot.label}`;
    selectedPlayer.append(context);
  }
  function addEvaluationClarity() {
    if (!latestEvaluation || resultContent.hidden) return;
    const value = latestEvaluation.value;
    const metricGrid = resultContent.querySelector('.metric-grid');
    if (metricGrid && !metricGrid.querySelector('[data-sizing-note]')) {
      const sizing = document.createElement('div');
      sizing.className = 'metric-box';
      sizing.dataset.sizingNote = 'true';
      sizing.innerHTML = `<span>Optional model stake suggestion</span><strong>$${Number(value.suggested_stake || 0).toFixed(2)}</strong>`;
      metricGrid.append(sizing);
    }
    if (latestEvaluation.prop.market === 'anytime_td' && !resultContent.querySelector('[data-td-note]')) {
      const note = document.createElement('div');
      note.className = 'result-section'; note.dataset.tdNote = 'true';
      note.innerHTML = `<h3>How to read the TD projection</h3><p>${Number(latestEvaluation.projection.mean).toFixed(2)} is an expected touchdown count, not a percentage chance of scoring. The discrete model converts it into the displayed chance of scoring 1+ touchdown.</p>`;
      resultContent.append(note);
    }
  }
  function renderLibrary(data) {
    activeSnapshot = data.snapshots.find(snapshot => snapshot.active) || null;
    if (!data.snapshots.length) {
      libraryList.innerHTML = '<p class="field-help">No saved projection sets yet. Import a weekly projection file to create one.</p>';
      return;
    }
    libraryList.innerHTML = data.snapshots.map(snapshot => `
      <article class="library-item ${snapshot.active ? 'active' : ''}">
        <div class="library-title-row"><div><h3>${escapeHtml(snapshot.label)}</h3><p>${escapeHtml(snapshot.source)} · NFL ${snapshot.season} Week ${snapshot.week}</p></div>${snapshot.active ? '<span class="active-tag">ACTIVE</span>' : ''}</div>
        <p>${snapshot.player_count} players · ${snapshot.projection_count} prop projections · ${snapshot.matchup_count} matchups · Imported ${new Date(snapshot.imported_at).toLocaleString()}</p>
        <div class="library-actions">
          ${snapshot.active ? '' : `<button class="library-action" data-activate="${snapshot.id}">Use this set</button>`}
          ${snapshot.active ? '' : `<button class="library-action danger" data-delete="${snapshot.id}">Delete permanently</button>`}
        </div>
      </article>`).join('');
    appendContext();
  }
  async function loadLibrary() {
    const data = await api('/api/projection-library');
    renderLibrary(data);
  }
  libraryButton.addEventListener('click', async () => {
    libraryModal.hidden = false;
    libraryList.innerHTML = '<p class="field-help">Loading projection sets…</p>';
    try { await loadLibrary(); } catch (error) { libraryList.innerHTML = `<p class="field-help">${escapeHtml(error.message)}</p>`; }
  });
  libraryList.addEventListener('click', async event => {
    const button = event.target.closest('button'); if (!button) return;
    const id = button.dataset.activate || button.dataset.delete; if (!id) return;
    try {
      if (button.dataset.delete) {
        if (!window.confirm('Delete this inactive projection set permanently? This cannot be undone.')) return;
        await api(`/api/projection-library/${id}`, { method: 'DELETE' });
        showMessage('Archived projection set deleted.');
      } else if (button.dataset.activate) {
        await api(`/api/projection-library/${id}/activate`, { method: 'POST' });
        document.querySelector('#clear-player').click();
        showMessage('Active projection set changed.');
      }
      await loadLibrary();
    } catch (error) { showMessage(error.message, true); }
  });
  new MutationObserver(appendContext).observe(selectedPlayer, { childList: true, subtree: true });
  new MutationObserver(() => setTimeout(addEvaluationClarity, 0)).observe(resultContent, { childList: true, subtree: true });
  const originalFetch = window.fetch.bind(window);
  window.fetch = async (...args) => {
    const response = await originalFetch(...args);
    const requestUrl = String(args[0]);
    if (response.ok && requestUrl.includes('/api/evaluator/evaluate')) {
      response.clone().json().then(data => { latestEvaluation = data; window.proplensLatestEvaluation = data; setTimeout(addEvaluationClarity, 0); }).catch(() => {});
    }
    return response;
  };

  document.addEventListener('click', async event => {
    const button = event.target.closest('#btn-upload-projections, #btn-paste-projections');
    if (!button) return;
    event.preventDefault(); event.stopImmediatePropagation();
    const metadata = importMetadata();
    if (!Number.isInteger(metadata.season) || !Number.isInteger(metadata.week)) return showMessage('Enter a whole-number season and week.', true);
    button.disabled = true; const originalText = button.textContent; button.textContent = 'Importing…';
    try {
      if (button.id === 'btn-upload-projections') {
        const file = document.querySelector('#projection-file').files[0];
        if (!file) throw new Error('Choose a projection file first.');
        const body = new FormData(); body.append('file', file); body.append('season', metadata.season); body.append('week', metadata.week); body.append('label', metadata.label);
        const data = await api('/api/upload/projections', { method: 'POST', body });
        showMessage(`${data.count} projections imported for Week ${metadata.week}.`);
      } else {
        const content = document.querySelector('#projection-paste').value.trim();
        if (!content) throw new Error('Paste projection text first.');
        const data = await api('/api/upload/paste', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ data_type: 'projections', content, ...metadata }) });
        showMessage(`${data.count} projections imported for Week ${metadata.week}.`);
      }
      document.querySelector('#import-modal').hidden = true;
      document.querySelector('#clear-player').click();
      await loadLibrary();
    } catch (error) { showMessage(error.message, true); }
    finally { button.disabled = false; button.textContent = originalText; }
  }, true);
  loadLibrary().catch(() => {});
})();
