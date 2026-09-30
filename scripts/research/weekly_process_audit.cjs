// Read-only weekly tracker analysis. Pass the NFL week as the first argument;
// without one it retains the original Week 1 behavior. Outputs JSON to stdout only.
const fs = require('fs');
const { dataPath, emit } = require('./report_output.cjs');
const crypto = require('crypto');
const assert = require('assert');
const r = n => Math.round(n * 100) / 100;
const sum = (a, k) => r(a.reduce((s,x)=>s+Number(typeof k==='function'?k(x):x[k]||0),0));
const files = ['data/tracked_bets.json','data/tracked_parlays.json'];
const raw = files.map(f=>fs.readFileSync(dataPath(f)));
const allB = JSON.parse(raw[0]).bets, allP=JSON.parse(raw[1]).parlays;
const manualCreditFile = 'data/manual_bonus_credits.json';
const manualCreditRaw = fs.existsSync(dataPath(manualCreditFile)) ? fs.readFileSync(dataPath(manualCreditFile)) : null;
const manualCredits = manualCreditRaw ? JSON.parse(manualCreditRaw).credits || [] : [];
const identity = x=>x.result_identity||{};
const requestedWeek = Number(process.argv[2] || 1);
if (!Number.isInteger(requestedWeek) || requestedWeek < 1 || requestedWeek > 18) throw new Error("Pass an NFL week from 1 through 18.");
const inWeek = x=>(x.season??identity(x).season)===2026 && (x.week??identity(x).week)===requestedWeek;
const b=allB.filter(inWeek).map(x=>({...x,kind:'straight'}));
const p=allP.filter(x=>inWeek(x)||x.legs.length&&x.legs.every(inWeek)).map(x=>({...x,kind:'parlay'}));
const all=[...b,...p];
assert.equal(new Set(all.map(x=>x.id)).size,all.length);
assert(all.every(x=>['won','lost','cashed_out','push','void','cancelled','pending','push_adjusted','void_adjusted'].includes(x.status)));
function summary(a){let s=a.filter(x=>!['pending','cancelled'].includes(x.status)),graded=s.filter(x=>!x.injury_adjusted_parlay_settlement),c=s.filter(x=>x.bet_type==='cash'),bon=s.filter(x=>x.bet_type==='bonus');return {n:a.length,w:graded.filter(x=>x.status==='won').length,l:graded.filter(x=>x.status==='lost').length,cashout:graded.filter(x=>x.status==='cashed_out').length,ungraded:s.length-graded.length,pending:a.filter(x=>x.status==='pending').length,cashN:c.length,cashStake:sum(c,'stake'),cashProfit:sum(c,'profit'),cashROI:sum(c,'stake')?r(sum(c,'profit')/sum(c,'stake')*100):null,bonusN:bon.length,bonusFace:sum(bon,'stake'),bonusCash:sum(bon,'profit'),conversion:sum(bon,'stake')?r(sum(bon,'profit')/sum(bon,'stake')*100):null};}
function groups(a,key){const m={};for(const x of a){let k=key(x);(m[k]??=[]).push(x)}return Object.fromEntries(Object.entries(m).map(([k,v])=>[k,summary(v)]));}
const team=t=>({HST:'HOU',BLT:'BAL',LA:'LAR',ARZ:'ARI',CLV:'CLE'}[t]||t);
function game(x){let t=team(x.team||identity(x).team),o=team(x.opponent||identity(x).opponent);return t&&o?[t,o].sort().join('–'):null;}
const structured=x=>x.entry_mode!=='free_text'&&x.market!=='manual';
const player=x=>structured(x)&&x.market!=='moneyline'&&(identity(x).player_key||x.player_name||'').toLowerCase().replace(/[^a-z0-9 ]/g,'').trim();
function exposure(key){const m={};for(const t of all){const ls=t.kind==='straight'?[t]:t.legs;for(const k of new Set(ls.map(key).filter(Boolean)))(m[k]??=[]).push(t)}return Object.entries(m).map(([key,v])=>({key,...summary(v),ids:v.map(x=>x.id.slice(0,8))})).sort((a,b)=>b.cashStake-a.cashStake||b.n-a.n);}
const ledger=all.map(x=>({id:x.id.slice(0,8),kind:x.kind,desc:x.description||x.player_name||x.legs.map(l=>l.player_name).join(' / '),status:x.status,type:x.bet_type,stake:x.stake,profit:x.profit,odds:x.decimal_odds??x.effective_decimal_odds,base:x.original_decimal_odds,boost:x.profit_boost_pct||0,market:x.market,side:x.side_label,line:x.line,origin:x.entry_origin,prob:x.model_win_probability,ev:x.expected_value_pct,later:(x.later_evaluations||[]).length,refresh:(x.evaluation_refreshes||[]).length,game:x.kind==='straight'?game(x):[...new Set(x.legs.map(game))].join('/'),legs:x.legs?.map(l=>({player:player(l)||l.description,market:l.market,side:l.side_label,line:l.line,prob:l.probability,game:game(l)}))}));
const receiptRows = all.flatMap(ticket => {
  const rows=[];
  const safety=ticket.safety_net_receipt;
  if(safety?.amount>0) rows.push({ticket, type:'safety_net', trigger:'lost_parlay_refund', amount:Number(safety.amount)});
  const protect=ticket.prop_protect_receipt;
  if(protect?.amount>0) rows.push({ticket, type:'prop_protect', trigger:protect.trigger||'unknown', amount:Number(protect.amount)});
  const injuryAdjusted=ticket.injury_adjusted_parlay_settlement;
  if(injuryAdjusted?.amount>0) rows.push({ticket, type:'injury_adjusted_parlay', trigger:'remaining_legs_regraded', amount:Number(injuryAdjusted.amount)});
  return rows;
}).map(({ticket,type,trigger,amount}) => {
  // A protection adjustment is not cash profit. It only removes a confirmed,
  // injury/refund loss from the process-review view, capped at the cash stake.
  const eligible= ticket.bet_type==='cash' && ticket.status==='lost' && (type==='safety_net'||trigger==='injury_void') && type!=='injury_adjusted_parlay';
  return {id:ticket.id.slice(0,8),kind:ticket.kind,type,trigger,status:ticket.status,stake:Number(ticket.stake||0),amount,processOffset:eligible?r(Math.min(amount,Number(ticket.stake||0))):0};
});
const scopedManualCredits=manualCredits.filter(credit => Number(credit.season)===2026 && Number(credit.week)===requestedWeek).map(credit=>({id:String(credit.id).slice(0,8),amount:Number(credit.amount||0)}));
const protectionOffset=sum(receiptRows,'processOffset');
const confirmedProtectionCredits=sum(receiptRows,'amount');
const manualCreditsReceived=sum(scopedManualCredits,'amount');
let mismatches=[];for(const x of all){if(!['won','lost','cashed_out'].includes(x.status))continue;let expected;if(x.status==='lost')expected=x.bet_type==='cash'?-x.stake:0;else if(x.status==='cashed_out')expected=x.settlement_amount-(x.bet_type==='cash'?x.stake:0);else if(x.kind==='straight')expected=x.stake*(x.decimal_odds-1);else expected=x.winning_total_return-(x.bet_type==='bonus'&&x.winning_return_includes_stake===false?0:x.stake);if(Math.abs(r(expected)-x.profit)>.011)mismatches.push({id:x.id,expected:r(expected),stored:x.profit});}
const evals=b.filter(x=>x.entry_origin==='evaluated'&&Number.isFinite(x.expected_value_pct));
const boostAnomalies=p.filter(x=>x.profit_boost_pct&&Math.abs(1+(x.original_decimal_odds-1)*(1+x.profit_boost_pct/100)-x.effective_decimal_odds)>.011).map(x=>({id:x.id.slice(0,8),base:x.original_decimal_odds,boost:x.profit_boost_pct,effective:x.effective_decimal_odds,formula:1+(x.original_decimal_odds-1)*(1+x.profit_boost_pct/100),status:x.status}));
const total={...summary(all)};
total.totalProfit=r(total.cashProfit+total.bonusCash);
const out={sources:[...files.map((f,i)=>({file:f,sha256:crypto.createHash('sha256').update(raw[i]).digest('hex')})),...(manualCreditRaw?[{file:manualCreditFile,sha256:crypto.createHash('sha256').update(manualCreditRaw).digest('hex')}]:[])],scope:{allB:allB.length,allP:allP.length,includedB:b.length,includedP:p.length,excluded:allB.length+allP.length-all.length},total,injuryAdjustedExceptions:p.filter(x=>x.injury_adjusted_parlay_settlement).map(x=>({id:x.id.slice(0,8),betType:x.bet_type,stake:x.stake,status:x.status,profit:x.profit,receipt:x.injury_adjusted_parlay_settlement})),protection:{officialCashAccounting:'Cash P/L and ROI remain unchanged. Bonus-credit face value is not cash profit.',confirmedBonusCredits:r(confirmedProtectionCredits+manualCreditsReceived),linkedProtectionCredits:confirmedProtectionCredits,unlinkedManualBonusCredits:manualCreditsReceived,injuryProtectionProcessOffset:protectionOffset,protectionAdjustedProcessProfit:r(total.totalProfit+protectionOffset),receiptRows,manualCreditRows:scopedManualCredits},structure:groups(all,x=>x.kind),fundingPromotion:groups(p,x=>x.bet_type+' / '+(x.profit_boost_pct?'boost':'no boost')),markets:groups(b,x=>x.market),sides:groups(b,x=>x.side_label),marketSides:groups(b,x=>x.market+' / '+x.side_label),stakes:groups(all,x=>x.kind+' / '+x.stake),origins:groups(b,x=>x.entry_origin),parlayLengths:groups(p,x=>x.bet_type+' / '+(x.legs.some(l=>!structured(l))?'unknown real leg count':x.legs.length)),parlayStructure:groups(p,x=>x.legs.some(l=>!game(l))?'unresolved':new Set(x.legs.map(game)).size===1?'same game':'cross game'),gameExposure:exposure(x=>structured(x)?game(x):null),playerExposure:exposure(player),playerMarketExposure:exposure(x=>player(x)?player(x)+' / '+x.market:null),marketExposure:exposure(x=>structured(x)?x.market:null),evals:{...summary(evals),negative:evals.filter(x=>x.expected_value_pct<0).map(x=>({id:x.id,name:x.player_name,ev:x.expected_value_pct,stake:x.stake,decision:x.decision_context||null})),modelExpectedProfit:sum(evals,x=>x.stake*x.expected_value_pct/100),integer:evals.filter(x=>Number.isInteger(x.line)).length,manualWithLater:b.filter(x=>x.entry_origin==='manual'&&x.later_evaluations?.length).length},coverage:{structuredLegs:p.flatMap(x=>x.legs).filter(structured).length,totalStoredLegs:p.flatMap(x=>x.legs).length,parlaysWithFreeText:p.filter(x=>x.legs.some(l=>!structured(l))).map(x=>x.id.slice(0,8)),legsWithProb:p.flatMap(x=>x.legs).filter(l=>Number.isFinite(l.probability)).length,settlementEvidence:all.filter(x=>x.settlement_evidence).length},profitMismatches:mismatches,boostAnomalies,ledger};
assert.equal(r(out.structure.straight.cashProfit+out.structure.parlay.cashProfit),out.total.cashProfit);
assert.equal(r(out.structure.straight.cashStake+out.structure.parlay.cashStake),out.total.cashStake);
emit(out, 'weekly-process-audit', 2026, requestedWeek, false);
