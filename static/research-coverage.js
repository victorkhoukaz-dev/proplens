/* Inspect exclusions without choosing or modifying a statistical match. */
(() => {
  const escape = value => String(value ?? '').replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
  const names = {
    no_player_stat_record: 'No player stat record — participation unknown',
    possible_name_mismatch: 'Possible name mismatch — review only',
    player_context_mismatch: 'Same name, different team/opponent',
    multiple_exact_stat_matches: 'Multiple exact stat matches',
    no_game_stat_records: 'No stat records for this game',
    final_stat_unavailable: 'Market stat unavailable',
    player_stats_unavailable: 'Season stats unavailable',
    imported_after_kickoff: 'Import at/after kickoff',
    missing_projection_identity: 'Missing player/team/opponent',
    schedule_unavailable_or_ambiguous: 'Schedule missing or ambiguous',
  };
  const shell = document.createElement('div');
  shell.className = 'modal-backdrop'; shell.hidden = true; shell.id = 'research-coverage-modal';
  shell.innerHTML = `<section class="modal-card research-drilldown-card" role="dialog" aria-modal="true" aria-labelledby="coverage-title"><button class="modal-close" aria-label="Close">×</button><p class="eyebrow">PHASE 5 · COVERAGE REVIEW</p><h2 id="coverage-title">Why projections were excluded</h2><p class="research-intro">Selected rows explain the final-stat matching gap. Import exclusions include repeated files and are counted separately. Possible candidates are clues for review, never accepted matches.</p><div class="research-drilldown-controls"><label>Player<input id="coverage-player" class="number-input" placeholder="Search player"></label><label>Stage<select id="coverage-stage"><option value="selected">Selected pre-kickoff rows</option><option value="import">Import exclusions</option><option value="">Both stages</option></select></label><label>Reason<select id="coverage-reason"></select></label><label>Market<select id="coverage-market"></select></label><label>Week<select id="coverage-week"></select></label></div><p id="coverage-counts" class="research-note"></p><div id="coverage-rows" class="research-drilldown-table"></div></section>`;
  document.body.append(shell);
  shell.querySelector('.research-drilldown-controls').insertAdjacentHTML('afterend', '<button type="button" id="coverage-check-participation" class="research-review-button">Preview participation</button><label>Participation result<select id="coverage-participation"><option value="">All results</option><option value="verified_played_zero">Verified played-zero</option><option value="verified_nonparticipant">Verified nonparticipant</option><option value="unresolved">Unresolved</option></select></label><p id="coverage-participation-summary" class="research-note">Preview only: main accuracy metrics stay unchanged. Snap counts alone never establish a zero.</p>');
  let rows = [], limit = 100;
  let scopeQuery = '';
  const $ = id => shell.querySelector(`#${id}`);
  shell.querySelector('.modal-close').onclick = () => { shell.hidden = true; };
  shell.onclick = event => { if (event.target === shell) shell.hidden = true; };
  function render() {
    const selected = rows.filter(row => (!$('coverage-participation').value || row.participation_preview?.status === $('coverage-participation').value) && (!$('coverage-stage').value || row.stage === $('coverage-stage').value) && (!$('coverage-reason').value || row.reason === $('coverage-reason').value) && (!$('coverage-market').value || row.market === $('coverage-market').value) && (!$('coverage-week').value || String(row.week) === $('coverage-week').value) && row.player_name.toLowerCase().includes($('coverage-player').value.trim().toLowerCase()));
    const counts = {};
    selected.forEach(row => { counts[row.reason] = (counts[row.reason] || 0) + 1; });
    $('coverage-counts').textContent = `${selected.length} filtered player-market rows. ` + Object.entries(counts).map(([key, count]) => `${names[key] || key}: ${count}`).join(' · ');
    $('coverage-rows').innerHTML = selected.slice(0, limit).map(row => `<article class="coverage-record"><strong>${escape(row.player_name)} · ${escape(row.market.replaceAll('_', ' '))} · ${Number(row.projection_mean).toFixed(1)} projected</strong><small>Week ${row.week} · ${escape(row.team || '?')} vs ${escape(row.opponent || '?')} · ${escape(row.snapshot_label)}</small><p>${escape(names[row.reason] || row.reason)}</p>${row.candidates.length ? `<small>Possible records: ${row.candidates.map(candidate => `${escape(candidate.player_key)} · ${escape(candidate.team)} vs ${escape(candidate.opponent)} · stat ${escape(candidate.actual_stat ?? 'unavailable')}`).join('; ')}</small>` : ''}</article>`).join('') || '<p class="field-help">No exclusions match these filters.</p>';
    if (selected.length > limit) $('coverage-rows').insertAdjacentHTML('beforeend', `<button type="button" id="coverage-more" class="research-review-button">Show next 100 (${selected.length - limit} remaining)</button>`);
    if ($('coverage-more')) $('coverage-more').onclick = () => { limit += 100; render(); };
    shell.querySelectorAll('.coverage-record').forEach((card, index) => {
      const preview = selected[index].participation_preview;
      if (!preview) return;
      const labels = {verified_played_zero:'Verified played-zero', verified_nonparticipant:'Verified nonparticipant', unresolved:'Unresolved', not_checked:'Not checked'};
      card.insertAdjacentHTML('beforeend', `<p><strong>${escape(labels[preview.status])}</strong> · ${escape(preview.detail)}${preview.offensive_snaps ? ` · ${preview.offensive_snaps} offensive snaps` : ''}${preview.in_game_injury ? ' · Verified in-game injury (research evidence)' : ''}</p><small>${preview.reviewed_at ? `Reviewed ${escape(preview.reviewed_at)} · ` : ''}${preview.sources.filter(url => /^https:\/\//.test(url)).map(url => `<a href="${escape(url)}" target="_blank" rel="noopener noreferrer">Evidence source</a>`).join(' · ')}</small>`);
    });
  }
  $('coverage-participation').addEventListener('input', () => { limit = 100; render(); });
  $('coverage-check-participation').onclick = async () => {
    const button = $('coverage-check-participation'); button.disabled = true;
    $('coverage-participation-summary').textContent = 'Checking participation sources…';
    try {
      const response = await fetch(`/api/research/mean-accuracy/unmatched?${scopeQuery}&participation=true&refresh_participation=true`);
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || 'Participation preview failed.');
      rows = data.records; limit = 100;
      const counts = data.participation.row_counts;
      $('coverage-participation-summary').textContent = `Preview only — selected player-market rows: ${counts.verified_played_zero || 0} verified played-zero · ${counts.verified_nonparticipant || 0} verified nonparticipant · ${counts.unresolved || 0} unresolved. Main metrics unchanged. ` + data.participation.sources.map(source => `Snap counts fetched ${source.fetched_at}${source.used_cache ? ' (cached)' : ''}.`).join(' ') + ' ' + data.participation.warnings.join(' ');
      render();
    } catch (error) { $('coverage-participation-summary').textContent = error.message; }
    finally { button.disabled = false; }
  };
  ['stage', 'reason', 'market', 'week', 'player'].forEach(key => $(`coverage-${key}`).addEventListener('input', () => { limit = 100; render(); }));
  document.querySelector('#research-report').addEventListener('click', async event => {
    if (!event.target.closest('#btn-review-unmatched')) return;
    shell.hidden = false; $('coverage-counts').textContent = 'Inspecting saved projections and cached stats…'; $('coverage-rows').innerHTML = '';
    const query = new URLSearchParams();
    const season = document.querySelector('#research-season').value.trim(), week = document.querySelector('#research-week').value.trim();
    if (season) query.set('season', season); if (week) query.set('through_week', week);
    scopeQuery = query.toString(); $('coverage-participation').value = '';
    $('coverage-participation-summary').textContent = 'Preview only: main accuracy metrics stay unchanged. Snap counts alone never establish a zero.';
    try {
      const response = await fetch(`/api/research/mean-accuracy/unmatched?${query}`);
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || 'Could not inspect coverage.');
      rows = data.records || []; limit = 100;
      ['reason', 'market', 'week'].forEach(key => {
        const values = [...new Set(rows.map(row => row[key]))].sort((a,b) => key === 'week' ? a-b : String(a).localeCompare(String(b)));
        $(`coverage-${key}`).innerHTML = '<option value="">All</option>' + values.map(value => `<option value="${escape(value)}">${escape(key === 'reason' ? names[value] || value : String(value).replaceAll('_', ' '))}</option>`).join('');
      });
      render();
    } catch (error) { $('coverage-counts').textContent = error.message; }
  });
})();
