/* Phase 2A: local straight-bet tracker with compact ledger controls. */
(() => {
  const $ = selector => document.querySelector(selector);
  const trackerModal = $('#tracker-modal'), saveModal = $('#save-bet-modal'), editModal = $('#edit-bet-modal'), cashoutModal = $('#cashout-modal'), laterEvaluationModal = $('#later-evaluation-modal'), laterEvaluationHistoryModal = $('#later-evaluation-history-modal');
  const trackerList = $('#tracker-list'), trackerSummary = $('#tracker-summary'), trackerIncludePending = $('#tracker-include-pending'), trackerIncludeParlays = $('#tracker-include-parlays'), trackerSearch = $('#tracker-search'), trackerSeasonFilter = $('#tracker-season-filter'), trackerWeekFilter = $('#tracker-week-filter'), trackerActivityFilter = $('#tracker-activity-filter'), trackerStatusFilter = $('#tracker-status-filter'), trackerTypeFilter = $('#tracker-type-filter'), trackerSort = $('#tracker-sort'), trackerVisibleCount = $('#tracker-visible-count'), trackerReportContext = $('#tracker-report-context'), betType = $('#tracker-bet-type'), stake = $('#tracker-stake'), bonusHelp = $('#tracker-bonus-help'), checkResults = $('#btn-check-results'), resultPreview = $('#result-preview'), resultPreviewSummary = $('#result-preview-summary'), resultPreviewList = $('#result-preview-list'), toggleResultPreview = $('#btn-toggle-result-preview'), suggestionsOnly = $('#btn-suggestions-only');
  let selectedBet = null, selectedLaterEvaluationBet = null, laterEvaluationPlayers = [], latestTrackerData = null, latestOverallSummary = null, latestResultPreview = null, showingSuggestionsOnly = false;
  const escapeHtml = value => String(value ?? '').replace(/[&<>'"]/g, char => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;' }[char]));
  const money = value => `$${Number(value || 0).toFixed(2)}`;
  const percent = value => value === null || value === undefined ? '—' : `${Number(value).toFixed(1)}%`;
  const toast = (message, error = false) => { const item = document.createElement('div'); item.className = `toast${error ? ' error' : ''}`; item.textContent = message; $('#toast-container').append(item); setTimeout(() => item.remove(), 4200); };
  const marketLabel = market => ({ passing_yards: 'Passing yards', passing_tds: 'Passing TDs', passing_interceptions: 'Passing interceptions', rushing_yards: 'Rushing yards', rushing_receiving_yards: 'Rushing + receiving yards', receiving_yards: 'Receiving yards', receptions: 'Receptions', anytime_td: 'Anytime TD', tackles_assists: 'Tackles + assists', solo_tackles: 'Solo tackles', sacks: 'Sacks', defensive_interceptions: 'Defensive interceptions', passes_defended: 'Passes defended', defensive_td: 'Defensive TD', moneyline: 'Moneyline', spread: 'Spread', game_total: 'Game total', team_total: 'Team total', custom_player_prop: 'Other player prop', custom_game_bet: 'Other game bet', custom: 'Other / custom bet' }[market] || String(market || '').replaceAll('_', ' '));
  const statusLabel = bet => bet.status === 'cashed_out' ? `Cashed out · ${money(bet.settlement_amount)} received` : bet.status === 'cancelled' ? 'Cancelled before start' : bet.status[0].toUpperCase() + bet.status.slice(1);
  async function api(url, options) { const response = await fetch(url, options); const data = await response.json().catch(() => ({})); if (!response.ok) throw new Error(data.detail || 'Something went wrong.'); return data; }

  function activityForBet(bet) { return { ...bet, activity_type: 'straight', game_season: bet.result_identity?.season ?? null, game_week: bet.result_identity?.week ?? null, activity_search: `${bet.description || ''} ${bet.player_name} ${bet.market} ${bet.category || ''} ${bet.position || ''} ${bet.team || ''} ${bet.opponent || ''}`, activity_sort_name: bet.description || bet.player_name }; }
  function parlayWeekContext(parlay) {
    if (parlay.season !== null && parlay.season !== undefined && parlay.week !== null && parlay.week !== undefined) return { season: parlay.season, week: parlay.week };
    const contexts = parlay.legs.map(leg => leg.result_identity).filter(identity => identity && Number.isInteger(Number(identity.season)) && Number.isInteger(Number(identity.week)) && Number(identity.season) >= 2020 && Number(identity.week) >= 1 && Number(identity.week) <= 25);
    if (contexts.length !== parlay.legs.length || !contexts.length) return { season: null, week: null };
    const [first] = contexts;
    return contexts.every(identity => Number(identity.season) === Number(first.season) && Number(identity.week) === Number(first.week)) ? { season: first.season, week: first.week } : { season: null, week: null };
  }
  function activityForParlay(parlay) { const context = parlayWeekContext(parlay); return { ...parlay, activity_type: 'parlay', game_season: context.season, game_week: context.week, activity_search: `${parlay.description || ''} ${parlay.legs.map(leg => `${leg.description || ''} ${leg.player_name} ${leg.market} ${leg.team || ''} ${leg.opponent || ''}`).join(' ')}`, activity_sort_name: parlay.description || parlay.legs[0]?.player_name || 'Parlay' }; }
  function hasWeekContext(item) { const season = Number(item.game_season), week = Number(item.game_week); return item.game_season !== null && item.game_season !== undefined && item.game_week !== null && item.game_week !== undefined && Number.isInteger(season) && Number.isInteger(week) && season >= 2020 && week >= 1 && week <= 25; }
  function reportFilteredActivity(activity) {
    const season = trackerSeasonFilter.value, week = trackerWeekFilter.value;
    return activity.filter(item => {
      if (season === 'unassigned') return !hasWeekContext(item);
      if (season !== 'all' && Number(item.game_season) !== Number(season)) return false;
      if (week === 'unassigned') return !hasWeekContext(item);
      return week === 'all' || Number(item.game_week) === Number(week);
    });
  }
  function populateWeekFilters(activity) {
    const currentSeason = trackerSeasonFilter.value, currentWeek = trackerWeekFilter.value;
    const seasons = [...new Set(activity.filter(hasWeekContext).map(item => Number(item.game_season)))].sort((a, b) => b - a);
    trackerSeasonFilter.innerHTML = `<option value="all">All seasons</option>${seasons.map(season => `<option value="${season}">${season} season</option>`).join('')}<option value="unassigned">Unassigned season/week</option>`;
    trackerSeasonFilter.value = [...trackerSeasonFilter.options].some(option => option.value === currentSeason) ? currentSeason : 'all';
    const selectedSeason = trackerSeasonFilter.value;
    const weeks = [...new Set(activity.filter(item => hasWeekContext(item) && (selectedSeason === 'all' || Number(item.game_season) === Number(selectedSeason))).map(item => Number(item.game_week)))].sort((a, b) => a - b);
    trackerWeekFilter.innerHTML = `<option value="all">All NFL weeks</option>${weeks.map(week => `<option value="${week}">Week ${week}</option>`).join('')}<option value="unassigned">Unassigned week</option>`;
    trackerWeekFilter.value = [...trackerWeekFilter.options].some(option => option.value === currentWeek) ? currentWeek : 'all';
  }
  function reportContextLabel() {
    const season = trackerSeasonFilter.value, week = trackerWeekFilter.value;
    if (season === 'unassigned' || week === 'unassigned') return 'Unassigned records only';
    if (season !== 'all' && week !== 'all') return `${season} · NFL Week ${week}`;
    if (season !== 'all') return `${season} NFL season · all weeks`;
    if (week !== 'all') return `All seasons · NFL Week ${week}`;
    return 'All NFL game weeks';
  }
  function summarizeActivity(activity) {
    const settled = activity.filter(item => item.status !== 'pending');
    const wagered = trackerIncludePending.checked ? activity : settled;
    const cashWagered = wagered.filter(item => item.bet_type === 'cash' && item.status !== 'cancelled');
    const cashSettled = settled.filter(item => item.bet_type === 'cash' && item.status !== 'cancelled');
    const bonusSettled = settled.filter(item => item.bet_type === 'bonus' && item.status !== 'cancelled');
    const bonusWagered = wagered.filter(item => item.bet_type === 'bonus' && item.status !== 'cancelled');
    const cashStaked = cashSettled.reduce((total, item) => total + Number(item.stake || 0), 0);
    const cashProfit = cashSettled.reduce((total, item) => total + Number(item.profit || 0), 0);
    const bonusProfit = bonusSettled.reduce((total, item) => total + Number(item.profit || 0), 0);
    const totalProfit = cashProfit + bonusProfit;
    return { pending: activity.filter(item => item.status === 'pending').length, cash_profit: cashProfit, bonus_profit: bonusProfit, total_profit: totalProfit, cash_wagered: cashWagered.reduce((total, item) => total + Number(item.stake || 0), 0), bonus_value_used: bonusWagered.reduce((total, item) => total + Number(item.stake || 0), 0), cash_roi_pct: cashStaked ? cashProfit / cashStaked * 100 : null, total_roi_on_cash_risk_pct: cashStaked ? totalProfit / cashStaked * 100 : null };
  }
  function filteredActivity(activity) {
    const search = trackerSearch.value.trim().toLowerCase(), activityType = trackerActivityFilter.value, status = trackerStatusFilter.value, type = trackerTypeFilter.value;
    return reportFilteredActivity(activity).filter(item => {
      const matchesSearch = !search || item.activity_search.toLowerCase().includes(search);
      const matchesActivity = activityType === 'all' || item.activity_type === activityType;
      const matchesStatus = status === 'all' || (status === 'settled' ? item.status !== 'pending' : item.status === status);
      const matchesSuggestions = !showingSuggestionsOnly || (item.activity_type === 'straight' && item.status === 'pending' && resultSuggestionFor(item)?.status === 'proposal');
      return matchesSearch && matchesActivity && matchesStatus && matchesSuggestions && (type === 'all' || item.bet_type === type);
    }).sort((a, b) => {
      if (trackerSort.value === 'pending_first' && (a.status === 'pending') !== (b.status === 'pending')) return a.status === 'pending' ? -1 : 1;
      if (trackerSort.value === 'player') return a.activity_sort_name.localeCompare(b.activity_sort_name);
      return (trackerSort.value === 'oldest' ? 1 : -1) * String(a.created_at).localeCompare(String(b.created_at));
    });
  }
  function resultSuggestionFor(bet) { return latestResultPreview?.proposals.find(item => item.bet_id === bet.id); }
  function inlineSuggestionMarkup(bet) {
    const suggestion = resultSuggestionFor(bet);
    if (bet.status !== 'pending' || suggestion?.status !== 'proposal') return '';
    const outcome = suggestion.proposed_result[0].toUpperCase() + suggestion.proposed_result.slice(1);
    return `<small class="inline-suggestion ${suggestion.proposed_result}">Suggested: ${outcome} · ${suggestion.actual_stat} ${escapeHtml(suggestion.stat_label)}</small>`;
  }
  function confirmedEvidenceMarkup(bet) {
    const evidence = bet.settlement_evidence;
    if (!evidence || evidence.source !== 'nflverse' || evidence.actual_stat === undefined) return '';
    return `<small class="inline-suggestion confirmed-evidence">Confirmed: nflverse · ${evidence.actual_stat} ${escapeHtml(evidence.stat_label)}</small>`;
  }
  function moreActions(bet, includeManualOutcomes = false) {
    const pendingActions = bet.status === 'pending' ? `${includeManualOutcomes ? `<button data-settle="won" data-bet-id="${bet.id}">Won</button><button data-settle="lost" data-bet-id="${bet.id}">Lost</button>` : ''}<button data-settle="push" data-bet-id="${bet.id}">Push</button><button data-cancel="${bet.id}">Cancel before start</button>` : '';
    const laterEvaluations = bet.later_evaluations || [];
    const laterEvaluationAction = bet.entry_origin === 'manual' && bet.category === 'player_prop' ? `<button data-later-evaluate="${bet.id}">${laterEvaluations.length ? 'Evaluate again' : 'Evaluate with projections'}</button>` : '';
    const laterHistoryAction = laterEvaluations.length ? `<button data-view-later-evaluations="${bet.id}">View later evaluation${laterEvaluations.length === 1 ? '' : 's'}</button>` : '';
    const editAttribute = bet.entry_origin === 'manual' ? `data-edit-manual="${bet.id}"` : `data-edit="${bet.id}"`;
    return `<details class="row-more"><summary aria-label="More actions for ${escapeHtml(bet.player_name)}">More</summary><div class="row-more-menu"><button ${editAttribute}>Edit</button>${laterEvaluationAction}${laterHistoryAction}${pendingActions}<button class="danger-action" data-delete="${bet.id}">Delete</button></div></details>`;
  }
  function rowMarkup(bet) {
    const week = bet.result_identity?.week;
    const matchup = bet.team ? `${escapeHtml(bet.team)}${bet.opponent ? ` vs ${escapeHtml(bet.opponent)}` : ''}${week ? ` · W${escapeHtml(week)}` : ''} · ` : (week ? `W${escapeHtml(week)} · ` : '');
    const profit = Number(bet.profit || 0), settled = bet.status !== 'pending';
    const suggestion = resultSuggestionFor(bet);
    const canConfirm = bet.status === 'pending' && suggestion?.status === 'proposal';
    const actions = bet.status === 'pending' ? (canConfirm ? `<button class="settle-win confirm-result" data-confirm-preview="${bet.id}" data-proposed-result="${suggestion.proposed_result}">Confirm ${suggestion.proposed_result[0].toUpperCase() + suggestion.proposed_result.slice(1)}</button><button data-cashout="${bet.id}">Cash out</button>${moreActions(bet, true)}` : `<button class="settle-win" data-settle="won" data-bet-id="${bet.id}">Won</button><button data-settle="lost" data-bet-id="${bet.id}">Lost</button><button data-cashout="${bet.id}">Cash out</button>${moreActions(bet)}`) : moreActions(bet);
    const evidence = trackerIncludeParlays.checked ? '' : confirmedEvidenceMarkup(bet);
    const title = bet.entry_origin === 'manual' ? bet.description || bet.player_name : bet.player_name;
    const selection = [bet.side_label, bet.line ?? ''].filter(value => value !== '').join(' ');
    const prop = [selection, marketLabel(bet.market)].filter(Boolean).join(' · ');
    const origin = bet.entry_origin === 'manual' ? `<span class="manual-entry-tag">Manual</span>${(bet.later_evaluations || []).length ? '<span class="later-evaluation-tag" title="Placed manually and evaluated later with imported projections">Later evaluated</span>' : ''}` : '<span class="evaluated-entry-tag">Evaluated</span>';
    return `<article class="tracked-bet ${bet.status === 'pending' ? 'is-pending' : 'is-settled'}"><div class="bet-identity">${origin}<strong>${escapeHtml(title)}</strong><span class="bet-prop">${escapeHtml(prop)}</span><small>${matchup}${Number(bet.decimal_odds).toFixed(2)} · ${bet.bet_type === 'bonus' ? 'Bonus' : 'Cash'} · ${money(bet.stake)}</small></div><div class="bet-status ${bet.status}"><span>${statusLabel(bet)}</span>${inlineSuggestionMarkup(bet)}${evidence}${settled ? `<strong class="${profit >= 0 ? 'positive' : 'negative'}">${profit >= 0 ? '+' : ''}${money(profit)}</strong>` : ''}</div><div class="settle-actions">${actions}</div></article>`;
  }
  function parlayRowMarkup(parlay) {
    const settled = parlay.status !== 'pending', profit = Number(parlay.profit || 0), legSummary = parlay.legs.map(leg => leg.description || [leg.player_name, leg.side_label, leg.line ?? ''].filter(Boolean).join(' ')).join(' · '), week = parlayWeekContext(parlay).week;
    const label = parlay.status === 'cashed_out' ? `Cashed out · ${money(parlay.settlement_amount)} received` : parlay.status === 'cancelled' ? 'Cancelled before start' : parlay.status === 'push_adjusted' ? 'Push-adjusted' : parlay.status === 'void_adjusted' ? 'Void-adjusted' : parlay.status[0].toUpperCase() + parlay.status.slice(1);
    const mixed = parlay.entry_origin === 'mixed';
    const title = parlay.entry_origin === 'manual' || mixed ? parlay.description || `${parlay.legs.length}-leg ${mixed ? 'mixed' : 'manual'} parlay` : `${parlay.legs.length}-leg parlay`;
    const tag = mixed ? '<span class="manual-entry-tag">Mixed parlay</span>' : parlay.entry_origin === 'manual' ? '<span class="manual-entry-tag">Manual parlay</span>' : '<span class="activity-tag">Parlay</span>';
    return `<article class="tracked-bet tracked-parlay-activity ${parlay.status === 'pending' ? 'is-pending' : 'is-settled'}"><div class="bet-identity"><strong>${tag}${escapeHtml(title)}</strong><span class="bet-prop">${Number(parlay.effective_decimal_odds).toFixed(2)} odds</span><small>${week ? `W${escapeHtml(week)} · ` : ''}${escapeHtml(legSummary)} · ${parlay.bet_type === 'bonus' ? 'Bonus' : 'Cash'} · ${money(parlay.stake)}</small></div><div class="bet-status ${parlay.status}"><span>${label}</span>${settled ? `<strong class="${profit >= 0 ? 'positive' : 'negative'}">${profit >= 0 ? '+' : ''}${money(profit)}</strong>` : ''}</div><div class="settle-actions"><button data-open-parlay-tracker="true">Open parlay</button></div></article>`;
  }
  function render(data) {
    latestTrackerData = data; window.proplensTrackedBets = data.bets;
    const activity = [...data.bets.map(activityForBet), ...(trackerIncludeParlays.checked ? data.parlays.map(activityForParlay) : [])];
    populateWeekFilters(activity);
    const reportActivity = reportFilteredActivity(activity);
    const s = summarizeActivity(reportActivity);
    latestOverallSummary = s;
    trackerSummary.innerHTML = `<div><span>Pending</span><strong>${s.pending}</strong></div><div><span>Cash-bet P/L</span><strong class="${s.cash_profit >= 0 ? 'positive' : 'negative'}">${s.cash_profit >= 0 ? '+' : ''}${money(s.cash_profit)}</strong></div><div><span>Bonus-bet cash profit</span><strong class="${s.bonus_profit >= 0 ? 'positive' : 'negative'}">${s.bonus_profit >= 0 ? '+' : ''}${money(s.bonus_profit)}</strong></div><div><span>Total net profit</span><strong class="${s.total_profit >= 0 ? 'positive' : 'negative'}">${s.total_profit >= 0 ? '+' : ''}${money(s.total_profit)}</strong></div><div><span>Cash-bet ROI</span><strong>${percent(s.cash_roi_pct)}</strong></div><div><span>Total ROI on cash risk</span><strong>${percent(s.total_roi_on_cash_risk_pct)}</strong></div><div><span>Cash wagered</span><strong>${money(s.cash_wagered)}</strong></div><div><span>Bonus value used</span><strong>${money(s.bonus_value_used ?? s.bonus_stake_used)}</strong></div>`;
    trackerReportContext.textContent = reportContextLabel();
    trackerActivityFilter.disabled = !trackerIncludeParlays.checked;
    if (!trackerIncludeParlays.checked) trackerActivityFilter.value = 'straight';
    $('#tracker-activity-column-label').textContent = trackerIncludeParlays.checked ? 'Activity' : 'Bet';
    const visibleActivity = filteredActivity(activity); trackerVisibleCount.textContent = `Showing ${visibleActivity.length} of ${reportActivity.length}`;
    trackerList.innerHTML = visibleActivity.length ? visibleActivity.map(item => item.activity_type === 'parlay' ? parlayRowMarkup(item) : rowMarkup(item)).join('') : '<p class="field-help tracker-empty">No activity matches these filters.</p>';
    renderOverall({ summary: s, include_parlays: trackerIncludeParlays.checked });
  }
  function renderOverall(data) {
    const s = data.summary, included = data.include_parlays;
    $('#overall-performance-context').textContent = included ? 'Straight bets + parlays' : 'Straight bets only';
    $('#overall-total-profit').textContent = `${s.total_profit >= 0 ? '+' : ''}${money(s.total_profit)}`;
    $('#overall-total-profit').className = s.total_profit >= 0 ? 'positive' : 'negative';
    $('#overall-total-roi').textContent = percent(s.total_roi_on_cash_risk_pct);
    $('#overall-cash-wagered').textContent = money(s.cash_wagered);
    $('#overall-bonus-used').textContent = money(s.bonus_value_used);
  }
  function previewMarkup(item) {
    const proposed = item.status === 'proposal' ? item.proposed_result : null;
    const outcome = proposed ? proposed[0].toUpperCase() + proposed.slice(1) : item.status === 'manual_required' ? 'Manual settlement' : item.status === 'game_not_final' || item.status === 'stats_unavailable' ? 'Waiting for stats' : item.status === 'source_error' ? 'Try again later' : 'Needs review';
    const actual = item.status === 'proposal' ? `Actual: ${item.actual_stat} ${escapeHtml(item.stat_label)}` : escapeHtml(item.message);
    const outcomeClass = proposed || (item.status === 'game_not_final' || item.status === 'stats_unavailable' ? 'waiting' : 'review');
    const line = item.line === null || item.line === undefined ? '' : ` ${item.line}`;
    return `<div class="result-preview-row"><div><strong>${escapeHtml(item.player_name)} · ${escapeHtml(marketLabel(item.market))}${line}</strong><small>${actual}</small></div><span class="result-preview-outcome ${outcomeClass}">${outcome}</span></div>`;
  }
  function renderResultPreview(data) {
    latestResultPreview = data;
    resultPreview.hidden = false;
    resultPreview.classList.remove('is-collapsed');
    toggleResultPreview.textContent = 'Collapse';
    toggleResultPreview.setAttribute('aria-expanded', 'true');
    const proposedItems = data.proposals.filter(item => item.status === 'proposal');
    const proposed = proposedItems.length;
    const sourceNote = data.sources.length ? ` · nflverse ${data.sources.map(source => `${source.season} ${source.used_cache ? 'cache' : 'refresh'}`).join(', ')}` : '';
    const outcomes = ['won', 'lost', 'push'].map(status => { const count = proposedItems.filter(item => item.proposed_result === status).length; return count ? `${count} ${status[0].toUpperCase() + status.slice(1)}` : ''; }).filter(Boolean).join(' · ');
    resultPreviewSummary.textContent = `${proposed} suggestion${proposed === 1 ? '' : 's'}${outcomes ? ` · ${outcomes}` : ''}${sourceNote}`;
    resultPreviewList.innerHTML = data.proposals.length ? data.proposals.map(previewMarkup).join('') : '<p class="field-help">There are no pending bets to check.</p>';
    showingSuggestionsOnly = false;
    suggestionsOnly.hidden = !proposed;
    suggestionsOnly.classList.remove('active');
    suggestionsOnly.textContent = `Suggestions only (${proposed})`;
  }
  function removeConfirmedSuggestion(betId) {
    if (!latestResultPreview) return;
    latestResultPreview = { ...latestResultPreview, proposals: latestResultPreview.proposals.filter(item => item.bet_id !== betId) };
    const remaining = latestResultPreview.proposals.filter(item => item.status === 'proposal').length;
    suggestionsOnly.hidden = !remaining;
    if (!remaining) { showingSuggestionsOnly = false; suggestionsOnly.classList.remove('active'); }
    const proposedItems = latestResultPreview.proposals.filter(item => item.status === 'proposal');
    const outcomes = ['won', 'lost', 'push'].map(status => { const count = proposedItems.filter(item => item.proposed_result === status).length; return count ? `${count} ${status[0].toUpperCase() + status.slice(1)}` : ''; }).filter(Boolean).join(' · ');
    const sourceNote = latestResultPreview.sources.length ? ` · nflverse ${latestResultPreview.sources.map(source => `${source.season} ${source.used_cache ? 'cache' : 'refresh'}`).join(', ')}` : '';
    resultPreviewSummary.textContent = `${remaining} suggestion${remaining === 1 ? '' : 's'}${outcomes ? ` · ${outcomes}` : ''}${sourceNote}`;
    resultPreviewList.innerHTML = latestResultPreview.proposals.length ? latestResultPreview.proposals.map(previewMarkup).join('') : '<p class="field-help">No pending bets remain in this result check.</p>';
    suggestionsOnly.textContent = showingSuggestionsOnly ? 'Show all bets' : `Suggestions only (${remaining})`;
  }
  async function loadTracker() {
    const pending = trackerIncludePending.checked, parlays = trackerIncludeParlays.checked;
    const [trackerData, parlayData] = await Promise.all([
      api(`/api/tracker/bets?include_pending=${pending}`),
      parlays ? api(`/api/tracker/parlays?include_pending=${pending}`) : Promise.resolve({ parlays: [] }),
    ]);
    render({ ...trackerData, parlays: parlayData.parlays });
  }
  window.proplensRefreshTracker = loadTracker;
  const findBet = id => (window.proplensTrackedBets || []).find(bet => bet.id === id);
  const supportedLaterEvaluationMarkets = new Set(['passing_yards', 'passing_tds', 'passing_interceptions', 'rushing_yards', 'receiving_yards', 'receptions', 'anytime_td']);
  const normalizeName = value => String(value || '').toLowerCase().replace(/[^a-z0-9]/g, '');
  async function openLaterEvaluation(bet) {
    if (!supportedLaterEvaluationMarkets.has(bet.market)) return toast('This manual market is not available in the projection evaluator yet.', true);
    if (!['over', 'under', 'yes'].includes(String(bet.side_label || '').toLowerCase()) || !Number.isFinite(Number(bet.line)) || !Number.isFinite(Number(bet.decimal_odds))) return toast('This manual bet needs an Over, Under, or Yes selection, an exact line, and decimal odds before it can be evaluated.', true);
    const data = await api(`/api/evaluator/players?q=${encodeURIComponent(bet.player_name || '')}&limit=20`);
    const exactName = normalizeName(bet.player_name);
    laterEvaluationPlayers = (data.players || []).filter(player => player.markets?.includes(bet.market) && normalizeName(player.player_name) === exactName);
    if (!laterEvaluationPlayers.length) return toast('No matching imported projection was found for this player and market. Import the correct projection set, or keep this bet track-only.', true);
    selectedLaterEvaluationBet = bet;
    $('#later-evaluation-summary').textContent = `${bet.player_name} ${bet.side_label} ${bet.line} · ${marketLabel(bet.market)} · ${Number(bet.decimal_odds).toFixed(2)} · ${money(bet.stake)}.`;
    $('#later-evaluation-player').innerHTML = laterEvaluationPlayers.map((player, index) => `<option value="${index}">${escapeHtml(player.player_name)} · ${escapeHtml(player.position)} · ${escapeHtml(player.team)} vs ${escapeHtml(player.opponent || '—')}</option>`).join('');
    laterEvaluationModal.hidden = false;
  }
  function showLaterEvaluationHistory(bet) {
    const snapshots = bet.later_evaluations || [];
    if (!snapshots.length) return;
    $('#later-evaluation-history-summary').textContent = `${bet.player_name} · placed manually, then evaluated ${snapshots.length} time${snapshots.length === 1 ? '' : 's'} after projections arrived.`;
    $('#later-evaluation-history-list').innerHTML = snapshots.slice().reverse().map(snapshot => {
      const when = snapshot.evaluated_at ? new Date(snapshot.evaluated_at).toLocaleString() : 'Saved earlier';
      const projection = Number(snapshot.projection?.mean);
      const probability = Number(snapshot.model?.win_probability);
      const fairOdds = Number(snapshot.model?.fair_decimal);
      const ev = Number(snapshot.value?.expected_value_pct);
      const prop = snapshot.prop || {};
      return `<article class="later-evaluation-history-item"><strong>${escapeHtml(snapshot.projection_snapshot_label || 'Imported projection set')}</strong><small>${escapeHtml(when)} · ${escapeHtml(prop.side_label || '')} ${escapeHtml(prop.line ?? '')} · ${escapeHtml(marketLabel(prop.market))}</small><div><span>Projection <b>${Number.isFinite(projection) ? projection.toFixed(1) : '—'}</b></span><span>Model win <b>${Number.isFinite(probability) ? percent(probability) : '—'}</b></span><span>Fair odds <b>${Number.isFinite(fairOdds) ? fairOdds.toFixed(2) : '—'}</b></span><span>EV <b class="${ev >= 0 ? 'positive' : 'negative'}">${Number.isFinite(ev) ? `${ev >= 0 ? '+' : ''}${ev.toFixed(2)}%` : '—'}</b></span></div></article>`;
    }).join('');
    laterEvaluationHistoryModal.hidden = false;
  }
  const refreshVisibleTracker = () => { if (latestTrackerData) render(latestTrackerData); };
  $('#btn-open-tracker').addEventListener('click', async () => { trackerModal.hidden = false; try { await loadTracker(); } catch (error) { toast(error.message, true); } });
  checkResults.addEventListener('click', async () => { checkResults.disabled = true; checkResults.textContent = 'Checking…'; try { const data = await api('/api/tracker/results/preview', { method: 'POST' }); renderResultPreview(data); refreshVisibleTracker(); toast(`Checked ${data.checked_pending} pending bet${data.checked_pending === 1 ? '' : 's'}. No results were changed.`); } catch (error) { toast(error.message, true); } finally { checkResults.disabled = false; checkResults.textContent = 'Check results'; } });
  toggleResultPreview.addEventListener('click', () => { const collapsed = resultPreview.classList.toggle('is-collapsed'); toggleResultPreview.textContent = collapsed ? 'Expand' : 'Collapse'; toggleResultPreview.setAttribute('aria-expanded', String(!collapsed)); });
  suggestionsOnly.addEventListener('click', () => { showingSuggestionsOnly = !showingSuggestionsOnly; suggestionsOnly.classList.toggle('active', showingSuggestionsOnly); suggestionsOnly.textContent = showingSuggestionsOnly ? 'Show all bets' : `Suggestions only (${latestResultPreview?.proposals.filter(item => item.status === 'proposal').length || 0})`; refreshVisibleTracker(); });
  trackerIncludePending.addEventListener('change', () => loadTracker().catch(error => toast(error.message, true)));
  trackerIncludeParlays.addEventListener('change', () => { trackerActivityFilter.value = trackerIncludeParlays.checked ? 'all' : 'straight'; loadTracker().catch(error => toast(error.message, true)); });
  trackerSeasonFilter.addEventListener('change', () => { trackerWeekFilter.value = 'all'; refreshVisibleTracker(); });
  trackerWeekFilter.addEventListener('change', refreshVisibleTracker);
  [trackerSearch, trackerActivityFilter, trackerStatusFilter, trackerTypeFilter, trackerSort].forEach(control => control.addEventListener('input', refreshVisibleTracker));
  $('#btn-start-later-evaluation').addEventListener('click', () => {
    const player = laterEvaluationPlayers[Number($('#later-evaluation-player').value)];
    if (!selectedLaterEvaluationBet || !player) return toast('Choose the imported player before evaluating.', true);
    window.proplensBeginLaterEvaluation?.(selectedLaterEvaluationBet, player);
  });
  document.addEventListener('click', async event => {
    const button = event.target.closest('#btn-attach-later-evaluation');
    if (!button) return;
    const target = window.proplensLaterEvaluationTarget?.();
    if (!target) return toast('Open this calculation from a manual tracked bet before attaching it.', true);
    button.disabled = true;
    try {
      await api(`/api/tracker/bets/${target.betId}/later-evaluation`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ player_name: target.playerName }) });
      window.proplensClearLaterEvaluationTarget?.();
      await loadTracker();
      toast('Later evaluation attached. The original wager remains a manual record.');
    } catch (error) { toast(error.message, true); } finally { button.disabled = false; }
  });
  document.addEventListener('click', event => { const button = event.target.closest('#btn-save-evaluation'); if (!button) return; const evaluation = window.proplensLatestEvaluation; if (!evaluation) return toast('Evaluate this prop before saving it.', true); $('#save-bet-summary').textContent = `${evaluation.prop.player_name} ${evaluation.prop.side_label} ${evaluation.prop.line} at ${Number(evaluation.prop.bet365_decimal).toFixed(2)}.`; stake.value = evaluation.value.entered_stake ?? 5; betType.value = 'cash'; bonusHelp.hidden = true; saveModal.hidden = false; });
  betType.addEventListener('change', () => { bonusHelp.hidden = betType.value !== 'bonus'; });
  $('#btn-save-tracked-bet').addEventListener('click', async event => { const evaluation = window.proplensLatestEvaluation, amount = Number(stake.value); if (!evaluation || !amount || amount <= 0) return toast('Enter the actual stake or bonus-bet value.', true); const button = event.currentTarget; button.disabled = true; try { const { prop, projection, model, value } = evaluation; await api('/api/tracker/bets', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ player_name: prop.player_name, team: prop.team, opponent: prop.opponent, market: prop.market, side_label: prop.side_label, line: prop.line, decimal_odds: prop.bet365_decimal, stake: amount, bet_type: betType.value, projection_mean: projection.mean, model_win_probability: model.win_probability, model_fair_decimal: model.fair_decimal, expected_value_pct: value.expected_value_pct, result_identity: evaluation.result_identity }) }); saveModal.hidden = true; toast('Saved as a pending bet.'); } catch (error) { toast(error.message, true); } finally { button.disabled = false; } });
  trackerList.addEventListener('click', async event => {
    const button = event.target.closest('button'); if (!button) return;
    if (button.dataset.laterEvaluate) { const bet = findBet(button.dataset.laterEvaluate); if (!bet) return; try { await openLaterEvaluation(bet); } catch (error) { toast(error.message, true); } return; }
    if (button.dataset.viewLaterEvaluations) { const bet = findBet(button.dataset.viewLaterEvaluations); if (bet) showLaterEvaluationHistory(bet); return; }
    if (button.dataset.editManual) return;
    if (button.dataset.openParlayTracker) { $('#btn-open-parlay-tracker').click(); return; }
    if (button.dataset.edit) { selectedBet = findBet(button.dataset.edit); if (!selectedBet) return; $('#edit-bet-summary').textContent = `${selectedBet.player_name} ${selectedBet.side_label} ${selectedBet.line}`; $('#edit-bet-type').value = selectedBet.bet_type; $('#edit-bet-stake').value = selectedBet.stake; $('#edit-bet-line').value = selectedBet.line; $('#edit-bet-odds').value = selectedBet.decimal_odds; $('#edit-bet-status').value = selectedBet.status; $('#edit-settlement-amount').value = selectedBet.settlement_amount ?? ''; editModal.hidden = false; return; }
    if (button.dataset.cashout) { selectedBet = findBet(button.dataset.cashout); if (!selectedBet) return; $('#cashout-summary').textContent = `${selectedBet.player_name} ${selectedBet.side_label} ${selectedBet.line} · stake ${money(selectedBet.stake)}`; $('#cashout-amount').value = ''; cashoutModal.hidden = false; return; }
    try { if (button.dataset.confirmPreview) { const result = button.dataset.proposedResult; if (!window.confirm(`Confirm ${result} from the final nflverse statistic shown for this bet? This saves the result and its source record.`)) return; await api(`/api/tracker/bets/${button.dataset.confirmPreview}/confirm-result-preview`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ expected_result: result }) }); removeConfirmedSuggestion(button.dataset.confirmPreview); toast(`Confirmed ${result} with nflverse evidence saved.`); } else if (button.dataset.delete) { if (!window.confirm('Delete this tracked bet permanently? This cannot be undone.')) return; await api(`/api/tracker/bets/${button.dataset.delete}`, { method: 'DELETE' }); toast('Tracked bet deleted.'); } else if (button.dataset.cancel) { if (!window.confirm('Cancel this pending bet? It will remain in history with $0.00 profit.')) return; await api(`/api/tracker/bets/${button.dataset.cancel}/settle`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ status: 'cancelled' }) }); } else if (button.dataset.settle) { await api(`/api/tracker/bets/${button.dataset.betId}/settle`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ status: button.dataset.settle }) }); } await loadTracker(); } catch (error) { toast(error.message, true); }
  });
  $('#btn-update-tracked-bet').addEventListener('click', async event => { if (!selectedBet) return; const status = $('#edit-bet-status').value, settlementText = $('#edit-settlement-amount').value.trim(); const body = { bet_type: $('#edit-bet-type').value, stake: Number($('#edit-bet-stake').value), line: Number($('#edit-bet-line').value), decimal_odds: Number($('#edit-bet-odds').value), status, settlement_amount: settlementText ? Number(settlementText) : null }; if (status === 'cashed_out' && !settlementText) return toast('Enter the actual cash-out amount.', true); const button = event.currentTarget; button.disabled = true; try { await api(`/api/tracker/bets/${selectedBet.id}`, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }); editModal.hidden = true; await loadTracker(); toast('Tracked bet corrected.'); } catch (error) { toast(error.message, true); } finally { button.disabled = false; } });
  $('#btn-confirm-cashout').addEventListener('click', async event => { if (!selectedBet) return; const amount = Number($('#cashout-amount').value); if (!Number.isFinite(amount) || amount < 0) return toast('Enter the actual cash-out amount.', true); const button = event.currentTarget; button.disabled = true; try { await api(`/api/tracker/bets/${selectedBet.id}/settle`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ status: 'cashed_out', settlement_amount: amount }) }); cashoutModal.hidden = true; await loadTracker(); toast('Cash-out recorded.'); } catch (error) { toast(error.message, true); } finally { button.disabled = false; } });
})();
