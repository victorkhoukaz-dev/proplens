// Read-only construction audit; no EV calculations or tracker writes.
const fs = require('fs'), crypto = require('crypto');
const { dataPath, emit } = require('./report_output.cjs');
const path = 'data/tracked_parlays.json', raw = fs.readFileSync(dataPath(path));
// Optional arguments: final week (default 3), season (default 2026).
const throughWeek = Number(process.argv[2] || 3);
const requestedSeason = Number(process.argv[3] || 2026);
if (!Number.isInteger(throughWeek) || throughWeek < 1 || throughWeek > 18 || !Number.isInteger(requestedSeason)) throw new Error('Pass a final NFL week from 1 through 18 and an optional season.');
const included = t => season(t) === requestedSeason && Number.isInteger(week(t)) && week(t) >= 1 && week(t) <= throughWeek;
const identity = x => x.result_identity || {};
const week = x => x.week ?? identity(x).week;
const season = x => x.season ?? identity(x).season;
const norm = t => ({ HST:'HOU', BLT:'BAL', LA:'LAR', ARZ:'ARI', CLV:'CLE' }[t] || t);
const team = l => norm(l.team || identity(l).team);
const game = l => { const a=team(l), b=norm(l.opponent || identity(l).opponent); return a && b ? [a,b].sort().join('|') : null; };
const structured = l => l.entry_mode !== 'free_text' && l.market !== 'manual';
const rows = JSON.parse(raw).parlays.filter(t => (included(t) || t.legs.length && t.legs.every(included) && new Set(t.legs.map(week)).size===1) && ['won','lost','cashed_out'].includes(t.status)).map(t=>{
  const ls=t.legs, desc=t.description || '', ctx=t.decision_context || {};
  const source = /\bme\b/i.test(desc) ? 'Self-built (Me)' : ctx.analyst || (/pendergrass/i.test(desc)?'Alex Pendergrass':/paul kelly/i.test(desc)?'Paul Kelly':/bostonsam/i.test(desc)?'bostonsam':'Unknown source');
  const markets=[...new Set(ls.filter(structured).map(l=>l.market))].sort();
  const games=[...new Set(ls.map(game).filter(Boolean))];
  const complete=ls.every(structured), completeGames=ls.every(l=>game(l));
  let teams='Unknown team structure';
  if (completeGames && games.length===1) { const counts={}; for(const l of ls) counts[team(l)]=(counts[team(l)]||0)+1; const c=Object.values(counts).sort((a,b)=>a-b); teams=c.length===1?'All legs one team':c[0]===1&&c[1]===1?'One leg per team (2 legs)': 'Both teams: '+c.join('+'); }
  const odds=t.effective_decimal_odds ?? t.decimal_odds;
  return {id:t.id.slice(0,8),week:week(t)||week(ls[0]),desc,source,status:t.status,funding:t.bet_type,stake:t.stake,profit:t.profit,odds,boost:!!t.profit_boost_pct,legCount:complete?ls.length:'Unknown actual count (free text)',markets,complete,gameStructure:completeGames?(games.length===1?'Same game':'Cross game'):'Incomplete game identity',teams,directions:complete?(ls.every(l=>l.side_label==='Over')?'All Over':ls.some(l=>l.side_label==='Under')?'Includes Under':ls.some(l=>l.side_label==='Yes')?'Over/TD or TD only':'Other'):'Unknown direction',legs:ls.map(l=>({player:l.player_name||l.description,market:l.market,side:l.side_label,line:l.line,team:team(l)}))};
});
const round=x=>Math.round(x*100)/100;
function stats(a) { const c=a.filter(t=>t.funding==='cash'), b=a.filter(t=>t.funding==='bonus'); const sum=(v,k)=>round(v.reduce((s,t)=>s+(+t[k]||0),0)); const wins=a.filter(t=>t.status==='won').length, losses=a.filter(t=>t.status==='lost').length; return {n:a.length,wins,losses,cashouts:a.filter(t=>t.status==='cashed_out').length,winRate:wins+losses?round(wins/(wins+losses)*100):null,cashStake:sum(c,'stake'),cashProfit:sum(c,'profit'),cashROI:sum(c,'stake')?round(sum(c,'profit')/sum(c,'stake')*100):null,bonusFace:sum(b,'stake'),bonusCash:sum(b,'profit')}; }
const group = fn => Object.fromEntries([...new Set(rows.map(fn))].map(k=>[k,stats(rows.filter(t=>fn(t)===k))]));
const out={source:{path,sha256:crypto.createHash('sha256').update(raw).digest('hex')},total:stats(rows),byWeek:group(t=>t.week),byFunding:group(t=>t.funding),byLegs:group(t=>t.legCount),byOdds:group(t=>!Number.isFinite(t.odds)?'Unknown':t.odds<5?'Below 5':t.odds<10?'5 to below 10':t.odds<20?'10 to below 20':'20 or above'),bySource:group(t=>t.source),byGame:group(t=>t.gameStructure),byTeam:group(t=>t.teams),byDirection:group(t=>t.directions),byMarketSet:group(t=>t.complete?t.markets.join(' + '):'Incomplete markets'),marketPresence:Object.fromEntries([...new Set(rows.flatMap(t=>t.markets))].map(m=>[m,stats(rows.filter(t=>t.markets.includes(m)))])),td:group(t=>t.markets.includes('anytime_td')?'Includes TD':t.complete?'No TD':'TD presence uncertain'),qbRush:group(t=>t.legs.some(l=>l.market==='rushing_yards'&&/maye|herbert|daniel jones|jayden daniels|joshua allen|jaxson dart|jalen hurts|shough|mahomes|jackson/i.test(l.player))?'Contains listed QB rush':'Other / unresolved'),boost:group(t=>t.boost?'Boosted':'Unboosted'),winners:rows.filter(t=>t.status==='won'||t.status==='cashed_out'),rows};
emit(out, 'parlay-observation', requestedSeason, throughWeek, true);
