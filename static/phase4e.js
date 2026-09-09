/* Phase 4E: reference-only player directory management. */
(() => {
  const $ = selector => document.querySelector(selector);
  const libraryModal = $('#library-modal');
  const projectionPanel = $('#projection-library-panel');
  const directoryPanel = $('#player-directory-panel');
  const tabs = [...document.querySelectorAll('[data-data-tab]')];
  const directoryFile = $('#player-directory-file');
  const importButton = $('#btn-import-player-directory');
  const clearButton = $('#btn-clear-player-directory');
  const summary = $('#player-directory-summary');

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
    if (!response.ok) throw new Error(data.detail || 'Something went wrong.');
    return data;
  }
  function showTab(tab) {
    const directory = tab === 'directory';
    projectionPanel.hidden = directory;
    directoryPanel.hidden = !directory;
    tabs.forEach(button => button.classList.toggle('active', button.dataset.dataTab === tab));
    if (directory) loadDirectory().catch(error => { summary.textContent = error.message; });
  }
  async function loadDirectory() {
    const data = await api('/api/player-directory');
    summary.innerHTML = data.count
      ? `<strong>${data.count} players</strong><span>${data.positions.join(', ') || 'positions unknown'} · ${data.team_count} teams · Updated ${data.updated_at ? new Date(data.updated_at).toLocaleString() : '—'}</span>`
      : '<strong>No player directory loaded</strong><span>Import a CSV to speed up manual player-prop entry.</span>';
    clearButton.hidden = !data.count;
  }
  tabs.forEach(button => button.addEventListener('click', () => showTab(button.dataset.dataTab)));
  $('#btn-open-library').addEventListener('click', () => setTimeout(() => loadDirectory().catch(() => {}), 0));
  $('#btn-manage-player-directory').addEventListener('click', () => {
    // The two dialogs use the same overlay layer. Close the manual form first
    // so the data library is always the visible, active dialog.
    $('#manual-bet-modal').hidden = true;
    libraryModal.hidden = false;
    showTab('directory');
  });
  directoryFile.addEventListener('change', () => { importButton.disabled = !directoryFile.files.length; });
  importButton.addEventListener('click', async () => {
    const file = directoryFile.files[0];
    if (!file) return;
    const originalText = importButton.textContent;
    importButton.disabled = true;
    importButton.textContent = 'Importing…';
    try {
      const body = new FormData();
      body.append('file', file);
      const data = await api('/api/player-directory/import', { method: 'POST', body });
      directoryFile.value = '';
      toast(`${data.count} directory players imported. They are not projections.`);
      await loadDirectory();
    } catch (error) { toast(error.message, true); }
    finally { importButton.disabled = !directoryFile.files.length; importButton.textContent = originalText; }
  });
  clearButton.addEventListener('click', async () => {
    if (!window.confirm('Clear the player directory? This removes only autocomplete reference players; saved bets and projection sets stay unchanged.')) return;
    try { await api('/api/player-directory', { method: 'DELETE' }); await loadDirectory(); toast('Player directory cleared.'); }
    catch (error) { toast(error.message, true); }
  });
})();
