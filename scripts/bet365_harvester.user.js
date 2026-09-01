// ==UserScript==
// @name         Bet365 NFL +EV Harvester (SharpEdge)
// @namespace    http://tampermonkey.net/
// @version      1.0.0
// @description  Automated 1-Click Bet365 NFL Player Props Ingestion for SharpEdge +EV Quantitative Betting App
// @author       SharpEdge Team
// @match        https://*.bet365.com/*
// @match        https://*.bet365.ca/*
// @icon         https://www.google.com/s2/favicons?sz=64&domain=bet365.com
// @grant        GM_xmlhttpRequest
// @grant        GM_setClipboard
// @connect      127.0.0.1
// @connect      localhost
// @run-at       document-idle
// ==/UserScript==

(function () {
    'use strict';

    const LOCAL_ENDPOINT = 'http://127.0.0.1:8000/api/ingest/bet365';

    // -------------------------------------------------------------
    // 1. UI WIDGET CREATION
    // -------------------------------------------------------------
    function createHarvesterHUD() {
        if (document.getElementById('sharpedge-harvester-hud')) return;

        const hud = document.createElement('div');
        hud.id = 'sharpedge-harvester-hud';
        hud.style.cssText = `
            position: fixed;
            top: 60px;
            right: 20px;
            z-index: 999999;
            background: rgba(10, 14, 23, 0.95);
            border: 1px solid rgba(0, 230, 153, 0.4);
            border-radius: 12px;
            padding: 14px 18px;
            box-shadow: 0 8px 32px rgba(0, 0, 0, 0.6);
            backdrop-filter: blur(8px);
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            color: #ffffff;
            width: 240px;
            user-select: none;
            transition: transform 0.2s ease, opacity 0.2s ease;
        `;

        hud.innerHTML = `
            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:10px; border-bottom:1px solid rgba(255,255,255,0.1); padding-bottom:6px;">
                <span style="font-weight:700; font-size:13px; color:#00e699; letter-spacing:0.5px;">⚡ SHARPEDGE HARVESTER</span>
                <span id="hud-close-btn" style="cursor:pointer; color:#888; font-size:16px;">×</span>
            </div>
            <div id="hud-status" style="font-size:11px; color:#94a3b8; margin-bottom:10px; line-height:1.3;">
                Ready to sync NFL props to local +EV terminal.
            </div>
            <div style="display:flex; flex-direction:column; gap:8px;">
                <button id="btn-sync-pass-yds" style="background:#00e699; color:#0a0e17; border:none; border-radius:6px; padding:8px 10px; font-weight:600; font-size:12px; cursor:pointer; display:flex; align-items:center; justify-content:center; gap:6px;">
                    🏈 Sync Passing Yards
                </button>
                <button id="btn-sync-all-props" style="background:#1e293b; color:#38bdf8; border:1px solid #38bdf8; border-radius:6px; padding:7px 10px; font-weight:600; font-size:12px; cursor:pointer; display:flex; align-items:center; justify-content:center; gap:6px;">
                    ⚡ Sync All NFL Props
                </button>
                <button id="btn-copy-clipboard" style="background:transparent; color:#94a3b8; border:1px solid #334155; border-radius:6px; padding:6px 10px; font-size:11px; cursor:pointer;">
                    📋 Copy Props JSON
                </button>
            </div>
            <div id="hud-stats-footer" style="margin-top:10px; font-size:10px; color:#64748b; text-align:center;">
                Terminal: <span style="color:#00e699;">127.0.0.1:8000</span>
            </div>
        `;

        document.body.appendChild(hud);

        // Bind events
        document.getElementById('hud-close-btn').onclick = () => {
            hud.style.display = 'none';
        };

        document.getElementById('btn-sync-pass-yds').onclick = () => {
            harvestCurrentView('player_pass_yds');
        };

        document.getElementById('btn-sync-all-props').onclick = () => {
            harvestCurrentView('all');
        };

        document.getElementById('btn-copy-clipboard').onclick = () => {
            copyExtractedPropsToClipboard();
        };
    }

    // -------------------------------------------------------------
    // 2. EXTRACTION ENGINE (DOM & PROPS)
    // -------------------------------------------------------------
    function extractPropsFromDOM(targetMarket = 'all') {
        const extracted = [];

        // Identify Market Group wrappers
        const marketGroups = document.querySelectorAll('[class*="MarketGroup"], [class*="gl-MarketGroup"]');

        marketGroups.forEach(group => {
            // Find market header label
            const headerEl = group.querySelector('[class*="MarketGroupButton_Text"], [class*="MarketGroupButton"], [class*="gl-MarketGroupButton"]');
            const headerText = headerEl ? headerEl.textContent.trim() : '';

            let marketCategory = 'player_pass_yds';
            const lowerHeader = headerText.toLowerCase();

            if (lowerHeader.includes('passing yard') || lowerHeader.includes('pass yard')) {
                marketCategory = 'player_pass_yds';
            } else if (lowerHeader.includes('rushing yard') || lowerHeader.includes('rush yard')) {
                marketCategory = 'player_rush_yds';
            } else if (lowerHeader.includes('receiving yard') || lowerHeader.includes('rec yard')) {
                marketCategory = 'player_rec_yds';
            } else if (lowerHeader.includes('reception')) {
                marketCategory = 'player_receptions';
            } else if (lowerHeader.includes('touchdown') || lowerHeader.includes('anytime td')) {
                marketCategory = 'player_anytime_td';
            } else if (lowerHeader.includes('passing touchdown') || lowerHeader.includes('pass td')) {
                marketCategory = 'player_pass_tds';
            } else {
                if (targetMarket !== 'all') return;
                marketCategory = headerText || 'player_pass_yds';
            }

            if (targetMarket !== 'all' && marketCategory !== targetMarket) {
                return;
            }

            // Find participant rows
            const rows = group.querySelectorAll('[class*="ParticipantRow"], [class*="gl-ParticipantRow"], [class*="sff-ParticipantRow"], tr');

            rows.forEach(row => {
                const nameEl = row.querySelector('[class*="Participant_Name"], [class*="ParticipantFixtureDetails_Name"], [class*="ParticipantFixtureDetails_Team"], [class*="Name"]');
                if (!nameEl) return;

                const playerName = nameEl.textContent.trim();
                if (!playerName || playerName.length < 2) return;

                // Extract Line / Handicap
                const handicapEl = row.querySelector('[class*="Handicap"], [class*="gl-Participant_Handicap"]');
                let lineVal = null;
                if (handicapEl) {
                    const match = handicapEl.textContent.match(/[\d\.]+/);
                    if (match) lineVal = parseFloat(match[0]);
                }

                // Extract Odds buttons
                const oddsEls = row.querySelectorAll('[class*="ParticipantOdds"], [class*="gl-ParticipantOdds"], [class*="Odds"]');

                if (oddsEls.length >= 2) {
                    // 2-way Over / Under
                    const overText = oddsEls[0].textContent.trim();
                    const underText = oddsEls[1].textContent.trim();

                    extracted.push({
                        player: playerName,
                        market: marketCategory,
                        line: lineVal,
                        over_odds: overText,
                        under_odds: underText,
                        bookmaker: 'bet365',
                        game: document.title.includes('vs') || document.title.includes('@') ? document.title : 'NFL Slate'
                    });
                } else if (oddsEls.length === 1) {
                    // 1-way (e.g. Anytime TD)
                    const priceText = oddsEls[0].textContent.trim();
                    extracted.push({
                        player: playerName,
                        market: marketCategory,
                        line: lineVal || 0.5,
                        price: priceText,
                        bookmaker: 'bet365',
                        game: document.title.includes('vs') || document.title.includes('@') ? document.title : 'NFL Slate'
                    });
                }
            });
        });

        return extracted;
    }

    // -------------------------------------------------------------
    // 3. DISPATCH TO LOCAL +EV BACKEND
    // -------------------------------------------------------------
    function harvestCurrentView(targetMarket = 'player_pass_yds') {
        const statusEl = document.getElementById('hud-status');
        statusEl.innerHTML = '<span style="color:#f59e0b;">⏳ Scanning Bet365 DOM...</span>';

        const props = extractPropsFromDOM(targetMarket);

        if (props.length === 0) {
            statusEl.innerHTML = '<span style="color:#ef4444;">⚠️ No player props visible. Click an NFL Player Props tab first.</span>';
            return;
        }

        statusEl.innerHTML = `<span style="color:#38bdf8;">📤 Sending ${props.length} props to terminal...</span>`;

        const payload = {
            bookmaker: 'bet365',
            sport: 'americanfootball_nfl',
            props: props,
            append: true
        };

        if (typeof GM_xmlhttpRequest !== 'undefined') {
            GM_xmlhttpRequest({
                method: 'POST',
                url: LOCAL_ENDPOINT,
                headers: { 'Content-Type': 'application/json' },
                data: JSON.stringify(payload),
                onload: function (response) {
                    handleIngestResponse(response.responseText, props.length);
                },
                onerror: function (err) {
                    handleIngestError(err);
                }
            });
        } else {
            fetch(LOCAL_ENDPOINT, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            })
            .then(res => res.json())
            .then(data => {
                handleIngestResponse(JSON.stringify(data), props.length);
            })
            .catch(err => {
                handleIngestError(err);
            });
        }
    }

    function handleIngestResponse(responseText, sentCount) {
        const statusEl = document.getElementById('hud-status');
        try {
            const data = JSON.parse(responseText);
            if (data.success) {
                statusEl.innerHTML = `<span style="color:#00e699; font-weight:600;">✅ Ingested ${sentCount} props!</span><br><span style="color:#94a3b8;">${data.opportunities_count || 0} +EV opportunities ready.</span>`;
            } else {
                statusEl.innerHTML = `<span style="color:#f59e0b;">⚠️ ${data.detail || 'Ingestion returned notice.'}</span>`;
            }
        } catch (e) {
            statusEl.innerHTML = `<span style="color:#00e699;">✅ Sent ${sentCount} props to +EV Terminal!</span>`;
        }
    }

    function handleIngestError(err) {
        const statusEl = document.getElementById('hud-status');
        statusEl.innerHTML = '<span style="color:#ef4444;">❌ Could not reach 127.0.0.1:8000. Is local app running?</span>';
        console.error('SharpEdge Harvester Error:', err);
    }

    function copyExtractedPropsToClipboard() {
        const props = extractPropsFromDOM('all');
        const jsonStr = JSON.stringify(props, null, 2);
        if (typeof GM_setClipboard !== 'undefined') {
            GM_setClipboard(jsonStr);
        } else {
            navigator.clipboard.writeText(jsonStr);
        }
        const statusEl = document.getElementById('hud-status');
        statusEl.innerHTML = `<span style="color:#38bdf8;">📋 Copied ${props.length} props JSON to clipboard!</span>`;
    }

    // -------------------------------------------------------------
    // 4. AUTO-INITIALIZE ON PAGE LOAD
    // -------------------------------------------------------------
    function init() {
        setTimeout(createHarvesterHUD, 1500);
        setInterval(() => {
            if (!document.getElementById('sharpedge-harvester-hud')) {
                createHarvesterHUD();
            }
        }, 3000);
    }

    if (document.readyState === 'complete' || document.readyState === 'interactive') {
        init();
    } else {
        window.addEventListener('DOMContentLoaded', init);
    }

})();
