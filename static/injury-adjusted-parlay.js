/* Receipt-only handling for a parlay regraded after an injured leg is removed. */
(() => {
  const money = value => `$${Number(value || 0).toFixed(2)}`;
  const escape = value => String(value ?? '').replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
  const action = parlay => ['pending', 'lost'].includes(parlay.status) && !parlay.injury_adjusted_parlay_settlement && !parlay.prop_protect_receipt
    ? `<button data-injury-adjusted-parlay="${escape(parlay.id)}">Injury-adjusted bonus credit</button>` : '';
  const badge = parlay => {
    const receipt = parlay.injury_adjusted_parlay_settlement;
    return receipt ? `<span class="safety-net-badge">Injury-adjusted · ${money(receipt.amount)} bonus received · ungraded</span>` : '';
  };
  let modal;
  function ensure() {
    if (modal) return;
    document.body.insertAdjacentHTML('beforeend', '<div class="modal-backdrop" id="injury-adjusted-parlay-modal" hidden><section class="modal-card safety-net-card decision-context-card"><button type="button" class="modal-close" id="iap-close">×</button><p class="eyebrow">PARLAY EXCEPTION</p><h2>Injury-adjusted bonus settlement</h2><div id="iap-content"></div><p id="iap-error" role="alert"></p><p class="field-help">This records a confirmed bonus-credit payout after Bet365 removed an injured leg and repriced the remaining parlay. It does not create cash profit. The original parlay is retained but excluded from ordinary win/loss outcome grading.</p></section></div>');
    modal = document.querySelector('#injury-adjusted-parlay-modal'); document.querySelector('#iap-close').onclick = () => modal.hidden = true;
  }
  function open(parlay) {
    ensure(); modal.hidden = false;
    const content = document.querySelector('#iap-content'), error = document.querySelector('#iap-error'); error.textContent = '';
    content.innerHTML = `<p>${escape(parlay.description || `${parlay.legs.length}-leg parlay`)} · ${parlay.bet_type === 'bonus' ? 'Bonus bet' : 'Cash bet'}.</p><label>Injured/cancelled leg<select id="iap-leg">${parlay.legs.map((leg, index) => `<option value="${index}">${escape(leg.description || leg.player_name || `Leg ${index + 1}`)}</option>`).join('')}</select></label><label>Actual bonus credit received ($)<input id="iap-amount" class="number-input" type="number" min="0.01" step="0.01"></label><button type="button" class="secondary-button" id="iap-save">Record injury-adjusted settlement</button>`;
    document.querySelector('#iap-save').onclick = async () => { const amount = Number(document.querySelector('#iap-amount').value), injured_leg_index = Number(document.querySelector('#iap-leg').value); if (!Number.isFinite(amount) || amount <= 0) return error.textContent = 'Enter the positive bonus-credit amount Bet365 issued.'; try { const response = await fetch(`/api/tracker/injury-adjusted-parlays/${parlay.id}/receipt`, {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({amount, injured_leg_index})}); const data = await response.json(); if (!response.ok) throw new Error(data.detail || 'Could not save the injury-adjusted settlement.'); modal.hidden = true; await window.proplensRefreshTracker(); } catch (exception) { error.textContent = exception.message; } };
  }
  document.addEventListener('click', event => { const button = event.target.closest('[data-injury-adjusted-parlay]'); if (!button) return; const parlay = (window.proplensTrackedParlays || []).find(item => item.id === button.dataset.injuryAdjustedParlay); if (parlay) open(parlay); });
  window.proplensInjuryAdjustedParlay = {action, badge};
})();
