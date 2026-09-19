/* Full-loss bonus refunds. Estimates never enter cash P/L or ROI. */
(() => {
  const $ = selector => document.querySelector(selector);
  const escape = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const money = value => `$${Number(value).toFixed(2)}`;
  const percent = value => `${(value * 100).toFixed(1)}%`;
  const preferenceKey = 'proplens.safety-net.conversion';
  function rememberedRate() { try { const value = localStorage.getItem(preferenceKey); const n = Number(value); return value !== null && Number.isFinite(n) && n >= 0 && n <= 100 ? n : 60; } catch { return 60; } }
  function estimate(stake, payout, refund, conversion, probability = null) {
    if (![stake, payout, refund, conversion].every(Number.isFinite) || stake <= 0 || payout < stake || refund <= 0 || refund > stake || conversion < 0 || conversion > 1) throw new Error('Enter a positive stake, a valid return, a refund no larger than the stake, and conversion from 0% to 100%.');
    const value = refund * conversion;
    return { value, ordinaryBreakEven: stake / payout, breakEven: payout === value ? 0 : (stake - value) / (payout - value), adjustedEv: probability === null ? null : probability * payout - stake + (1 - probability) * value };
  }
  function mount(anchor, {stake, type = () => 'cash', changed = () => {}}) {
    const root = document.createElement('section'); root.className = 'safety-net-input';
    root.innerHTML = `<label class="safety-net-toggle"><input type="checkbox" class="sn-enabled"> Safety net — refunded in bonus bets if lost</label><div class="sn-fields" hidden><div class="sn-grid"><label>Bonus refund if lost ($)<input class="number-input sn-refund" type="number" min="0.01" step="0.01"></label><label>Estimated bonus cash value (%)<input class="number-input sn-rate" type="number" min="0" max="100" step="1" value="${rememberedRate()}"></label></div><p class="field-help">Conversion is an assumption: a $5 bonus at 60% is estimated to return $3 cash on average. It already includes the chance of losing the bonus wager. Actual P/L and ROI count cash only.</p><p class="field-help">Check your offer’s leg count, minimum odds, refund cap, and whether other promotions can be combined.</p></div>`;
    anchor.insertAdjacentElement('afterend', root);
    const enabled = root.querySelector('.sn-enabled'), refund = root.querySelector('.sn-refund'), rate = root.querySelector('.sn-rate'), fields = root.querySelector('.sn-fields');
    let automaticRefund = true;
    function sync() { root.hidden = type() !== 'cash'; fields.hidden = !enabled.checked || root.hidden; refund.disabled = rate.disabled = fields.hidden; if (automaticRefund) refund.value = Number(stake()) > 0 ? Number(stake()).toFixed(2) : ''; }
    enabled.addEventListener('change', () => { sync(); changed(); });
    refund.addEventListener('input', () => { automaticRefund = false; changed(); });
    rate.addEventListener('input', () => { const n = Number(rate.value); if (rate.value.trim() && Number.isFinite(n) && n >= 0 && n <= 100) { try { localStorage.setItem(preferenceKey, String(n)); } catch {} } changed(); });
    const control = {
      root, sync,
      value() { sync(); if (!enabled.checked || type() !== 'cash') return null; if (!rate.value.trim() || !refund.value.trim()) throw new Error('Enter the bonus refund and conversion assumption.'); const offer = { refund_amount: Number(refund.value), conversion_rate: Number(rate.value) / 100 }; estimate(Number(stake()), Number(stake()) * 2, offer.refund_amount, offer.conversion_rate); return offer; },
      set(offer) { enabled.checked = !!offer; automaticRefund = !offer; refund.value = offer?.refund_amount ?? ''; rate.value = offer ? offer.conversion_rate * 100 : rememberedRate(); sync(); },
    };
    sync(); return control;
  }
  function result(offer, stake, payout, probability = null, sameGame = false) {
    if (!offer) return '';
    const e = estimate(stake, payout, offer.refund_amount, offer.conversion_rate, probability);
    return `<section class="safety-net-result"><strong>Safety net</strong><p>${money(offer.refund_amount)} bonus refund if lost · estimated cash value <b>${money(e.value)}</b></p><p>Break-even win chance <b>${percent(e.breakEven)}</b> · without safety net ${percent(e.ordinaryBreakEven)}</p>${e.adjustedEv === null ? '' : `<p>${sameGame ? 'Independent-reference' : 'Independent-baseline'} EV including estimated bonus value: <b>${e.adjustedEv >= 0 ? '+' : '−'}${money(Math.abs(e.adjustedEv))}</b></p>`}<small>Cash at risk: ${money(stake)}. Bonus recovery is not guaranteed.${sameGame ? ' Same-game probability is not correlation-adjusted; this is not a true SGP value verdict.' : ''}</small></section>`;
  }
  function badge(ticket) {
    if (!ticket.safety_net) return '';
    const receipt = ticket.safety_net_receipt;
    const links = ticket.safety_net_summary?.links || [];
    let text;
    if (!receipt) {
      text = ticket.status === 'lost' ? `Safety net · ${money(ticket.safety_net.refund_amount)} bonus expected` : ticket.status === 'pending' ? `Safety net · ${money(ticket.safety_net.refund_amount)} bonus if lost` : 'Safety net · no loss refund';
    } else if (links.some(link => link.needs_review)) {
      text = `Safety net · ${money(receipt.amount)} bonus received · linked wager needs review`;
    } else if (links.some(link => link.status === 'pending')) {
      text = `Safety net · ${money(receipt.amount)} bonus received · linked bonus wager pending`;
    } else if (links.length) {
      const cashProfit = links.reduce((total, link) => total + Number(link.cash_profit || 0), 0);
      text = `Safety net · ${money(receipt.amount)} received · ${money(ticket.safety_net_summary?.remaining || 0)} unlinked · linked cash ${cashProfit >= 0 ? '+' : '−'}${money(Math.abs(cashProfit))}`;
    } else {
      text = `Safety net · ${money(receipt.amount)} received · ${money(ticket.safety_net_summary?.remaining || 0)} unlinked`;
    }
    return `<button type="button" class="safety-net-badge" data-safety-net="${escape(ticket.id)}">${text}</button>`;
  }
  async function api(url, body) { const response = await fetch(url, body === undefined ? undefined : {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(body)}); const data = await response.json(); if (!response.ok) throw new Error(Array.isArray(data.detail) ? data.detail.map(d => d.msg).join(' ') : data.detail || 'Could not save safety-net details.'); return data; }
  let modal, sourceId, bonusTarget;
  function ensureModal() {
    if (modal) return;
    document.body.insertAdjacentHTML('beforeend', `<div class="modal-backdrop" id="safety-net-modal" hidden><section class="modal-card safety-net-card" role="dialog" aria-modal="true" aria-labelledby="safety-net-title"><button type="button" class="modal-close" id="sn-close" aria-label="Close">×</button><h2 id="safety-net-title">Safety-net refund</h2><div id="sn-content"></div><p id="sn-error" role="alert"></p><p class="field-help">Bonus credit and its estimated value never increase actual P/L. Only cash paid from the linked wager counts as profit.</p></section></div>`);
    modal = $('#safety-net-modal'); $('#sn-close').onclick = () => modal.hidden = true;
    modal.addEventListener('click', event => { if (event.target === modal) modal.hidden = true; });
    document.addEventListener('keydown', event => { if (event.key === 'Escape' && !modal.hidden) modal.hidden = true; });
    modal.addEventListener('click', async event => {
      const button = event.target.closest('[data-sn-action]'); if (!button) return;
      button.disabled = true; $('#sn-error').textContent = '';
      try {
        const action = button.dataset.snAction;
        if (action === 'receipt' || action === 'clear') {
          const amount = action === 'clear' ? null : Number($('#sn-received').value);
          if (amount !== null && (!Number.isFinite(amount) || amount <= 0)) throw new Error('Enter the actual positive bonus amount received.');
          await api(`/api/tracker/safety-nets/${sourceId}/receipt`, {amount});
        } else if (action === 'link') {
          const selection = $('#sn-candidate').value; if (!selection) throw new Error('Choose a tracked bonus wager.');
          const [kind, ticket_id] = selection.split(':');
          await api(`/api/tracker/safety-nets/${sourceId}/link`, {kind, ticket_id});
        } else if (action === 'source-link') {
          const source = $('#sn-source').value; if (!source) throw new Error('Choose a received refund.');
          await api(`/api/tracker/safety-nets/${source}/link`, bonusTarget);
        } else if (action === 'unlink') {
          await api(`/api/tracker/safety-nets/${button.dataset.source || sourceId}/link`, {kind:button.dataset.kind, ticket_id:button.dataset.ticket, unlink:true});
        }
        await window.proplensRefreshTracker?.(); await window.proplensRefreshParlayTracker?.();
        await open(sourceId, bonusTarget);
      } catch (error) { $('#sn-error').textContent = error.message; }
      finally { button.disabled = false; }
    });
  }
  function choice(candidate) { return `${candidate.kind === 'parlay' ? 'Parlay' : 'Straight'} · ${candidate.description} · ${money(candidate.stake)} · ${candidate.status} · ${candidate.created_at.slice(0,10)}`; }
  async function open(id, target = null) {
    ensureModal(); sourceId = id; bonusTarget = target; modal.hidden = false; $('#sn-content').textContent = 'Loading…'; $('#sn-error').textContent = '';
    try {
      const report = await api('/api/tracker/safety-nets');
      if (target) {
        const linked = report.sources.find(s => s.links.some(l => l.kind === target.kind && l.ticket_id === target.ticket_id));
        const options = report.sources.filter(s => s.receipt && s.remaining > 0 && s.status === 'lost');
        $('#sn-content').innerHTML = linked ? `<p>Linked to ${escape(linked.description)}.</p><button type="button" data-sn-action="unlink" data-source="${escape(linked.id)}" data-kind="${target.kind}" data-ticket="${escape(target.ticket_id)}">Unlink wager</button>` : `<label>From safety-net refund<select id="sn-source"><option value="">Choose a received refund</option>${options.map(s => `<option value="${escape(s.id)}">${escape(s.description)} · ${money(s.remaining)} unlinked · ${s.created_at.slice(0,10)}</option>`).join('')}</select></label><p class="field-help">Linking is optional. Record the bonus receipt on the losing parlay first. The whole bonus stake must fit within one refund.</p><button type="button" class="secondary-button" data-sn-action="source-link" ${options.length ? '' : 'disabled'}>Link refund</button>`;
        return;
      }
      const source = report.sources.find(s => s.id === id); if (!source) throw new Error('This parlay no longer has a safety net.');
      const receipt = source.receipt;
      const candidates = report.candidates.filter(c => c.stake <= source.remaining + .001);
      $('#sn-content').innerHTML = `<p>${escape(source.description)}</p><p>Expected refund: <b>${money(source.offer.refund_amount)} bonus</b> · conversion assumption ${percent(source.offer.conversion_rate)}</p>${source.status === 'lost' ? `<label>Actual bonus received ($)<input type="number" class="number-input" id="sn-received" min="0.01" max="${source.offer.refund_amount}" step="0.01" value="${receipt?.amount ?? source.offer.refund_amount}"></label><div class="sn-actions"><button type="button" data-sn-action="receipt">${receipt ? 'Correct received amount' : 'Mark received'}</button>${receipt ? '<button type="button" data-sn-action="clear">Clear receipt</button>' : ''}</div>` : `<p>${source.status === 'pending' ? 'A bonus refund is expected only if this eligible parlay loses.' : 'This result does not trigger the full-loss refund.'}</p>`}${receipt ? `<p>Confirmed ${money(receipt.amount)} bonus received · ${money(source.remaining)} not linked to a wager.</p><p class="field-help">Track your bonus bet using the normal bonus-bet form, then select it here. An unlinked amount is not a verified Bet365 balance.</p><label>Resulting bonus wager<select id="sn-candidate"><option value="">Choose a tracked bonus wager</option>${candidates.map(c => `<option value="${c.kind}:${escape(c.ticket_id)}">${escape(choice(c))}</option>`).join('')}</select></label><button type="button" data-sn-action="link" ${candidates.length ? '' : 'disabled'}>Link bonus wager</button><div class="sn-links">${source.links.map(l => `<div><strong>${escape(l.description)}</strong><p>${l.needs_review ? 'Needs review: wager was changed, cancelled, or removed. Unlink and correct the match.' : `${escape(l.status)} · ${l.cash_profit === null ? 'Cash result pending' : `Cash profit ${money(l.cash_profit)}`}`}</p><button type="button" data-sn-action="unlink" data-kind="${l.kind}" data-ticket="${escape(l.ticket_id)}">Unlink wager</button></div>`).join('')}</div>` : ''}`;
    } catch (error) { $('#sn-content').textContent = ''; $('#sn-error').textContent = error.message; }
  }
  document.addEventListener('click', event => { const source = event.target.closest('[data-safety-net]'); if (source) open(source.dataset.safetyNet); const bonus = event.target.closest('[data-safety-net-bonus]'); if (bonus) open(null, {kind:bonus.dataset.bonusKind, ticket_id:bonus.dataset.safetyNetBonus}); });
  window.proplensSafetyNet = {mount, result, badge, estimate, open};
})();
