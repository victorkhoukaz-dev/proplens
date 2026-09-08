# PropLens Product Plan

Last updated: September 8, 2026

This document is the working product reference for PropLens. It records the direction we agreed on, what exists today, what still needs testing, and the order in which we intend to build it. It is a plan, not a promise that every later feature must be implemented unchanged.

## Product direction

PropLens is a practical NFL betting assistant built around three jobs:

1. Evaluate a manually entered Bet365 player-prop price against an imported projection model.
2. Record and review bets with accurate cash, bonus-bet, ROI, and settlement accounting.
3. Evaluate and track parlays with a transparent independent-leg baseline, manual sensitivity inputs, boost accounting, and clearly separated manual-only records.

Automatic Bet365 Canada player-prop odds remain desirable, but they are not the foundation of the product until a legal, reliable, affordable source proves exact coverage for the required player, market, side, and line.

## Phase 1 — Manual prop evaluator

Status: implemented and under continued real-world testing.

### Phase 1A — Fast evaluation workflow

- Import FantasyPoints-style projections.
- Search and select a player.
- Show the player's imported projections immediately.
- Select a supported market and side.
- Enter the exact Bet365 line and odds.
- Calculate model win probability, fair price, expected value, and optional stake result.
- Preserve exact-line push handling.

### Phase 1.1 — Projection-set management

- Keep one active projection set at a time.
- Preserve older inactive sets for reference or reactivation.
- Allow permanent deletion of inactive sets.
- Show season, week, source, import time, and player count.
- Avoid a separate archive concept.

### Model assumptions

- Yardage markets currently use a lognormal distribution.
- Default coefficient of variation is market-first:
  - Passing yards: 0.28
  - Rushing yards: 0.42
  - Receiving yards: 0.55
- Player position is only a fallback when a market coefficient is unavailable.
- A valid custom volatility override from imported data takes precedence.
- Receptions and touchdown counts use separate count-distribution models.
- These coefficients are preliminary assumptions, not proven player-specific probabilities.

## Phase 2 — Convenience and bet tracking

### Phase 2A — Straight-bet tracker

Status: implemented and user-tested; continue validating it during real weekly use.

- Save an evaluated straight bet as pending.
- Track cash bets and bonus bets separately.
- Record win, loss, push, cash-out, or cancellation.
- Edit and correct bets after saving or settlement.
- Delete an erroneous tracker entry.
- Calculate cash-bet profit, bonus-bet cash profit, total net profit, cash ROI, total ROI on cash risk, cash wagered, and bonus value used.
- Include or exclude pending bets from wager totals.
- Provide compact search, filtering, sorting, and row actions for a 20–30 bet week.

#### Manual straight-bet extension — implemented and user-tested

- Provide a fast **Track manual bet** path for a player without projections, an unsupported market, or a bet placed before projections are published.
- This is track-only: it records the wager but never invents a projection, fair price, EV, or model probability.
- Collect the normal financial details plus optional season, NFL week, team, opponent, and supported-market identity details.
- Allow result-check suggestions only when the manual entry has complete compatible identity data; otherwise label it **Manual settlement required**.
- Label manual records separately from evaluated records so future model reporting cannot treat them as model-backed decisions.

### Phase 2B — Faster player and game selection

Status: implemented and being tested.

- Browse projected players without typing a name first.
- Filter by position.
- Rank players by a selected projection market.
- Group and browse players by game for easy comparison with a Bet365 event page.
- Show recently evaluated players for quick repeat access.

### Phase 2C — Automatic result checking

Status: provider feasibility, reliable identities, preview-only checks, and explicit source-backed confirmations have passed historical 2025 UI testing. Touchdown grading remains the next separate safety step.

#### Phase 2C.0 — Provider proof

- **Decision:** use nflverse as the primary no-cost source for the first settlement-preview implementation.
- A live nflverse 2025 Week 1 test returned the required game/player identity plus passing, rushing, receiving, reception, interception, and touchdown fields in one weekly file.
- A live API-Sports test successfully found a finished 2024 game and returned team-specific Passing, Rushing, and Receiving player groups. The schedule request reported 335 games, and the player-stat request reported both teams.
- The API-Sports key authenticated correctly, but the provider returned a free-plan restriction for season 2025: only seasons 2022 through 2024 were accessible to this account. This makes its free tier unsuitable for current-season automatic settlement.
- API-Sports remains a technically viable future paid/faster option, but no purchase is recommended for Phase 2C.
- The API-Sports public guide and the account's live response disagree about free-plan season access. Treat the live account response as authoritative for this project and re-test before any future purchase.
- Live ESPN public-endpoint tests of completed 2024 and 2025 games returned final-game status, stable ESPN event/player IDs, and exact passing, rushing, and receiving box-score values. The 2025 Cowboys-Eagles result matched the nflverse benchmark for Barkley, Lamb, and Hurts. It required no account, API key, or observed quota.
- ESPN is not a documented/supported public API. Use it only as an optional same-day **preview or fallback** source; keep nflverse as the primary next-morning source before any result is applied.
- Keep API calls server-side, cache responses locally, and never store the key in source control.
- Keep this probe completely separate from real tracker settlement.
- Remaining risks to test during implementation: data publication timing, missing-player behavior, late stat corrections, player-name/ID matching, and touchdown grading exceptions.

#### Phase 2C.1 — Reliable bet identity

- Save season, week, normalized player name, team, opponent, matchup key, position, and projection-snapshot context on new tracker entries.
- Do not guess a home/away game ID or scheduled kickoff from a projection file; resolve those later from a verified result source.
- Populate these automatically from the selected player, projection set, and schedule.
- Keep source-specific identifiers separate: nflverse and ESPN use different game/player IDs. The first implementation should retain a canonical game/team/player identity and use ESPN only for preview matching.
- Leave existing tracker records unchanged; label their missing result context as legacy during the result-preview phase instead of silently rewriting their history.
- Do not require repetitive manual data entry.

#### Phase 2C.2 — Settlement preview

- **Implemented and tested:** a **Check results** action downloads the relevant nflverse season once per click, caches it locally, and checks all pending bets with saved result context.
- **Implemented:** the tracker displays the actual stat and a proposed win/loss/push for supported passing, rushing, receiving-yard, and reception props.
- **Implemented and tested:** it distinguishes missing legacy context, game not final/published, unmatched player review, source errors, and unsupported markets.
- **Safety rule:** it is preview only; it does not change any tracked-bet result. User approval through the existing manual tracker controls remains required during the trial period.
- **UX implemented and tested:** suggestions can collapse to a one-line summary, filter to actionable rows only, and display the proposed result plus actual statistic inline on the relevant Pending rows.
- **Deferred:** touchdown markets deliberately remain manual review until Phase 2C.4 sportsbook-grading work is tested.

#### Phase 2C.3 — Safe settlement rules

- **Implemented and tested:** an explicit **Confirm Won/Lost/Push** action rechecks the individual Pending bet against cached nflverse final data before settling it.
- **Implemented and tested:** ordinary passing/rushing/receiving yards and receptions support wins, losses, and exact whole-number pushes; a missing player is never treated as zero.
- **Implemented and tested:** confirmation refuses cash-outs, cancellations, already settled bets, waiting rows, unmatched players, unsupported markets, and changed proposals.
- **Implemented and tested:** each confirmed result stores nflverse as the source, source timestamp, observed statistic, season/week, reason, and a settlement-history entry. The settled row shows the concise evidence line in the tracker.
- **Safety rule retained:** no result is applied simply by running Check results; the user must approve each exact proposed outcome.

#### Phase 2C.4 — Touchdowns and sportsbook exceptions

- **Implemented and tested:** Anytime TD can suggest and explicitly confirm **Won** only when nflverse records at least one rushing or receiving touchdown for the exact matched player/game.
- **Implemented:** passing touchdowns are excluded from scorer logic.
- **Safety rule:** no rushing/receiving TD never becomes an automatic loss; return/recovery touchdown possibilities, participation/no-action, voids, postponements, and Bet365-specific grading remain **Needs review**.
- **Current evidence:** Bet365 Canada states that American-football wagers are settled from official-provider/competition statistics, with independent evidence or its own statistics used where necessary. PropLens therefore treats nflverse as helpful confirmation evidence, not the final authority in a scoring exception.
- **Still deferred:** play-by-play-backed treatment of return/recovery TDs and explicit participation/no-action detection before any broader automatic TD result support.

### Future revisit — Optional result automation and faster stats

This is intentionally **not the next phase**. The current Check results → explicit Confirm workflow is the default until it has been proven through real NFL weeks.

#### Future option 2C.5 — High-confidence automatic settlement

- Reconsider only after at least 3–4 live NFL weeks, approximately 20–30 confirmed standard-market bets, and no unexplained matching or Bet365-settlement discrepancy.
- Automatically apply only final-game, exact-player, exact-game, supported-market matches; keep touchdown exceptions and ambiguous cases for review.
- Recheck recently settled games for stat corrections and request approval before changing an earlier recorded result.
- While PropLens remains local, any check still requires the app to be open; true unattended checks would require an always-running deployment.
- Preserve the current explicit confirmation workflow as a permanent fallback and user preference, even if automation is later introduced.

#### Future option — Faster/supplementary sports-stat API

- nflverse remains the free primary source for next-morning final-stat checks.
- Revisit ESPN or a paid/supported provider only if same-day updates, stronger game-status data, or play-by-play touchdown exception coverage becomes valuable enough to justify the added complexity or cost.
- Re-test any provider's current access, pricing, terms, and data coverage at the time of the decision; do not assume a past free tier remains available.

## Phase 3 — Parlays

Status: Phase 3A (independence baseline and Bet365 boosts), Phase 3B (personal sensitivity), and Phase 3C.0 (local parlay ledger) are implemented and user-tested. Automatic result suggestions for parlay legs remain deferred.

### Phase 3A — Manual parlay evaluator

- Build a parlay from multiple evaluated legs.
- Accept the actual Bet365 combined decimal odds.
- Calculate the independent-leg baseline by multiplying leg probabilities.
- Show independent fair odds, actual sportsbook odds, break-even probability, and estimated EV.
- Show the actual win return separately from the long-run estimated net result on an optional stake.
- Clearly label the result as an independence baseline when correlation is not modeled.
- Detect same-game legs and explicitly state that neither a positive nor negative independence-baseline EV is a correlation-adjusted value verdict.
- Show the price gap versus independent fair odds as a comparison, not as proof of value for a same-game parlay.

#### Bet365 parlay boosts — implemented and user-tested

- Accept an optional Bet365 **profit boost %** in the manual parlay calculator.
- Calculate boosted total return as `stake + ((decimal odds − 1) × stake × (1 + boost percentage))`.
- Show the original Bet365 odds alongside the effective boosted return/odds, and use the boosted value for break-even chance, independence-baseline EV, win outcome, and long-run estimated net result.
- Provide an optional **Actual boosted return** override for unusual offers; when entered, it is authoritative over the percentage calculation.
- State clearly that PropLens calculates from the entered promotion details only and does not verify Bet365 eligibility, maximum stakes, or offer terms.
- Save original odds, boost details, and final boosted payout in the Phase 3C parlay record.

### Phase 3B — Belief and sensitivity analysis

- Let the user adjust confidence in one or more legs without pretending the adjustment is objective.
- Show how the parlay probability and EV change under those assumptions.
- Make the difference between model probability and user belief explicit.

### Phase 3C — Parlay tracker

- Save a parlay and all component legs, plus original odds, effective boosted odds, boost/return treatment, stake type, and calculated winning return.
- **Phase 3C.0 — implemented and user-tested:** manually track pending, won, lost, push-adjusted, void-adjusted, cashed-out, and cancelled parlays; correct saved financial details or settlement later; delete a test/error record deliberately. Keep straight and parlay ledgers separate, but offer a concise optional combined overall-performance roll-up for total profit, ROI on cash risk, cash wagered, and bonus value used.
- **Manual-parlay extension — hybrid builder implemented, awaiting user testing:** provide a separate **Track manual parlay** path for bets whose legs were not evaluated, are unsupported, or were placed before projections were available. Guided legs retain category, player, position, teams, market, side, and line; unrestricted free-text legs remain available in the same parlay. Record 2–10 mixed legs, combined Bet365 odds, stake, cash/bonus type, optional profit boost or exact return, and optional shared season/week. Label it **Manual** and save no probability, fair odds, or EV.
- **Phase 3C.1 — future:** reuse Phase 2C game/player identifiers and result checks for every eligible leg, then present a cautious whole-parlay settlement suggestion only when all required legs have final, unambiguous results.
- Apply sportsbook repricing rules cautiously when a leg pushes or is voided.

### Phase 3D — Correlation layer

- Begin with transparent warnings for known same-game relationships.
- Compare independent fair odds with the actual correlated Bet365 SGP price.
- Add estimated joint probabilities only when historical data or a defensible model supports them.
- Never describe a guessed correlation adjustment as proven EV.

## Phase 4 — Tracker coverage and reporting

Status: manual coverage and unified activity are implemented. Weekly filtering is the next planned reporting step after hybrid-parlay testing.

### Phase 4A — Manual tracking entry

- **Implemented and user-tested:** provide a fast **Track manual bet** path for player props without projections, defensive props, and game/other bets such as moneylines, spreads, totals, and custom bets.
- Save an explicit **Manual** origin and blank model fields so tracking-only records are never treated as model-backed decisions in later research; newly saved evaluator bets receive an explicit **Evaluated** origin.
- Allow free player entry while suggesting players from the active projection set; selecting one can fill its team, opponent, and position. A separate player-directory import can be considered later if defensive-prop use makes it worthwhile.
- Keep Phase 4A manual entries on manual settlement for this first safe version. Precisely identified supported player props can be connected to result checks in a later extension after their identity and grading behavior are tested.
- Reuse existing cash/bonus accounting, ROI, result correction, cash-out, cancellation, and deletion behavior.
- Capture description/category, player and position where applicable, team, opponent, market, side, optional line, decimal odds, stake, cash/bonus type, and optional season plus NFL week.
- Default new entries to the current configured season and offer an editable, date-based NFL-week suggestion; remember the last manually chosen week only for the current browser session.
- Permit full correction of a manual entry through its own edit form while preserving the rule that it contains no model evaluation.

### Phase 4B — Unified overall activity view

- **Implemented and user-tested:** when **Include parlays in overall view** is enabled, show straight bets and parlays together in the Bet tracker list.
- Keep a parlay as one labelled activity row with compact leg detail and an Open action; do not duplicate each leg as a separate bet row.
- Provide an activity filter for all activity, straight bets, or parlays while retaining cash/bonus, status, search, and sort filters.
- Keep the dedicated Parlay tracker as the detailed place to settle, adjust, or edit a parlay.

### Phase 4C — NFL-week filtering and weekly ROI

- Add reporting filters and summary metrics by NFL season and NFL week, rather than calendar date entered.
- Apply the existing cash-bet ROI, total ROI on cash risk, cash wagered, bonus value used, and profit definitions consistently within the selected week.
- Keep records without reliable season/week context visibly **Unassigned** and exclude them from weekly totals rather than guessing.
- A parlay belongs to a week only when all legs have the same reliable NFL week; otherwise mark it Unassigned until corrected.
- Require a manually entered season/week for a manual bet to appear in an NFL-week report.

## Phase 5 — Model improvement

Status: future research.

- Backtest projection accuracy by market and position.
- Calibrate market coefficients from historical game logs.
- Explore a market-by-position matrix.
- Add player-specific volatility only when sample size is sufficient.
- Measure calibration, bias, and closing-line performance rather than judging the model from isolated bets.
- Preserve the current simple model as an understandable baseline.

### Evaluation history and projection updates

- Treat every saved evaluated bet as an immutable decision-time model snapshot: projection-set ID/label, projection, market, line, odds, model probability, fair odds, and EV.
- Never recalculate or overwrite that snapshot after a later projection import.
- Use the original snapshot and eventual actual result for future calibration and accuracy research.
- If an updated projection needs inspection later, save it as a separate timestamped comparison evaluation rather than modifying the original tracked bet.

## Phase 6 — Additional reporting and bankroll insight

Status: optional future work.

- Weekly and season performance summaries.
- Results by market, player position, odds range, and model-edge range.
- Cash versus bonus-bet performance.
- Bankroll curve and drawdown.
- Optional closing-line-value tracking when closing odds can be entered or obtained reliably.
- Exportable tracker history and backups.

## External odds acquisition

Status: monitor and test opportunistically; do not make it the core workflow yet.

- Continue evaluating low-cost providers only with exact Bet365 Canada/international player-prop coverage tests.
- Require the same player, market, side, and exact line.
- Minimize credits by inspecting raw responses and using saved fixtures.
- Do not return to browser DOM harvesting as the primary strategy unless new evidence changes its reliability and terms risk.

## Current recommended order

1. Test the hybrid manual-parlay builder with guided legs, free-text legs, and a mixture of both; verify editing and overall ROI inclusion.
2. Build Phase 4C NFL-week filters and weekly ROI now that straight bets and manual parlays can carry season/week context.
3. Use PropLens through real NFL workflow and record friction before expanding data-entry automation.
4. Return to Phase 3C.1 for cautious, confirm-only parlay result suggestions when real parlay tracking justifies it.
5. Treat Phase 3D correlation and Phase 5 model improvement as later evidence-driven work.

## Potential future options — revisit after real workflow testing

These are deliberately **not committed implementation phases**. This section is the single place to review ideas that may become valuable after real use reveals which problems are frequent enough to solve.

- **Bet365 screenshot-to-draft:** upload or paste a bet-slip screenshot, extract its legs, combined odds, stake, boost, and return, then prefill a reviewable manual-parlay draft. Never save directly from OCR; require the user to verify every extracted number and side first.
- **Evaluated-leg shortcut inside the manual-parlay builder:** allow an already evaluated PropLens leg to be inserted beside guided manual and free-text legs. Revisit if users frequently build mixed model-backed/manual parlays; preserve per-leg origin so the whole parlay is never mislabelled as fully modeled.
- **Complete active-player directory:** import or maintain offensive and defensive NFL rosters so manual player entry can autocomplete beyond the active projection file. Revisit after defensive-prop usage shows whether projection-only suggestions are insufficient.
- **High-confidence automatic settlement (Phase 2C.5):** consider only after several live weeks demonstrate reliable matching and no unexplained Bet365 grading discrepancies. Keep explicit confirmation as a permanent fallback.
- **Faster or supported sports-stat provider:** reconsider ESPN, API-Sports, or another provider if same-day results, play-by-play, or supported service guarantees justify cost and integration work. Re-test price and coverage before any purchase.
- **Parlay result suggestions (Phase 3C.1):** suggest a whole-parlay outcome only when every required structured leg has an exact, final, supported result. Keep free-text and ambiguous legs on manual settlement.
- **Correlation estimates (Phase 3D):** move beyond the independence baseline only with defensible historical evidence. Do not convert a guessed relationship into an EV verdict.
- **Player-specific model calibration:** estimate volatility by market, position, and eventually player only after enough actual results exist; preserve the current simple model as the comparison baseline.
- **Reliable automatic Bet365 odds acquisition:** periodically reassess legal, affordable sources for exact Bet365 Canada/international player-prop lines. Do not revive brittle browser harvesting without materially better evidence.
- **Deployment and multi-device access:** consider durable hosted storage only if local-only use becomes inconvenient; do not publish tracker data or move it to a paid service without an explicit privacy and cost decision.

## Product safety principles

- The app assists decisions; it does not place wagers.
- Model EV is an estimate, not guaranteed value.
- No automatic financial-history change without an exact match and an audit record.
- No paid service, publication, or destructive data change without explicit approval.
- Build in meaningful, testable stages and pause for user feedback between stages.
