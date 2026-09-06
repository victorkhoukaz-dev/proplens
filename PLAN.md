# PropLens Product Plan

Last updated: September 5, 2026

This document is the working product reference for PropLens. It records the direction we agreed on, what exists today, what still needs testing, and the order in which we intend to build it. It is a plan, not a promise that every later feature must be implemented unchanged.

## Product direction

PropLens is a practical NFL betting assistant built around three jobs:

1. Evaluate a manually entered Bet365 player-prop price against an imported projection model.
2. Record and review bets with accurate cash, bonus-bet, ROI, and settlement accounting.
3. Eventually evaluate and track parlays, including a transparent independent-leg baseline and carefully labelled correlation adjustments.

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

Status: implemented and being tested.

- Save an evaluated straight bet as pending.
- Track cash bets and bonus bets separately.
- Record win, loss, push, cash-out, or cancellation.
- Edit and correct bets after saving or settlement.
- Delete an erroneous tracker entry.
- Calculate cash-bet profit, bonus-bet cash profit, total net profit, cash ROI, total ROI on cash risk, cash wagered, and bonus value used.
- Include or exclude pending bets from wager totals.
- Provide compact search, filtering, sorting, and row actions for a 20–30 bet week.

### Phase 2B — Faster player and game selection

Status: implemented and being tested.

- Browse projected players without typing a name first.
- Filter by position.
- Rank players by a selected projection market.
- Group and browse players by game for easy comparison with a Bet365 event page.
- Show recently evaluated players for quick repeat access.

### Phase 2C — Automatic result checking

Status: provider feasibility and identity capture completed; preview-only result checking is now ready for live user testing.

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

- **Implemented:** a **Check results** action downloads the relevant nflverse season once per click, caches it locally, and checks all pending bets with saved result context.
- **Implemented:** the tracker displays the actual stat and a proposed win/loss/push for supported passing, rushing, receiving-yard, and reception props.
- **Implemented:** it distinguishes missing legacy context, game not final/published, unmatched player review, source errors, and unsupported markets.
- **Safety rule:** it is preview only; it does not change any tracked-bet result. User approval through the existing manual tracker controls remains required during the trial period.
- **Deferred:** touchdown markets deliberately remain manual review until Phase 2C.4 sportsbook-grading work is tested.

#### Phase 2C.3 — Safe settlement rules

- Settle ordinary over/under lines, including exact whole-number pushes.
- Never infer zero merely because a player row is missing.
- Ignore cash-outs, cancellations, and already settled bets.
- Record result source, source timestamp, observed statistic, and settlement reason.
- Make repeated checks idempotent and preserve an audit trail.

#### Phase 2C.4 — Touchdowns and sportsbook exceptions

- Test anytime-TD logic separately.
- Exclude passing touchdowns from scorer bets.
- Review returns, fumble recoveries, participation, voids, postponed games, and Bet365-specific grading rules.
- Keep ambiguous outcomes as review items.

#### Phase 2C.5 — Optional high-confidence automation

- Consider automatic settlement only after preview results are proven accurate across real weeks.
- Automatically apply only final-game, exact-player, exact-game, supported-market matches.
- Recheck recent games for stat corrections and request approval before changing a previous result.
- While PropLens remains local, check on demand or when the tracker opens; true unattended schedules require an always-running deployment.

## Phase 3 — Parlays

Status: planned after the straight-bet evaluator and tracker are dependable.

### Phase 3A — Manual parlay evaluator

- Build a parlay from multiple evaluated legs.
- Accept the actual Bet365 combined decimal odds.
- Calculate the independent-leg baseline by multiplying leg probabilities.
- Show independent fair odds, actual sportsbook odds, break-even probability, and estimated EV.
- Clearly label the result as an independence baseline when correlation is not modeled.

### Phase 3B — Belief and sensitivity analysis

- Let the user adjust confidence in one or more legs without pretending the adjustment is objective.
- Show how the parlay probability and EV change under those assumptions.
- Make the difference between model probability and user belief explicit.

### Phase 3C — Parlay tracker

- Save a parlay and all component legs.
- Reuse Phase 2C game/player identifiers and result checking for every leg.
- Track pending, won, lost, push-adjusted, void-adjusted, cashed-out, and cancelled parlays.
- Apply sportsbook repricing rules cautiously when a leg pushes or is voided.

### Phase 3D — Correlation layer

- Begin with transparent warnings for known same-game relationships.
- Compare independent fair odds with the actual correlated Bet365 SGP price.
- Add estimated joint probabilities only when historical data or a defensible model supports them.
- Never describe a guessed correlation adjustment as proven EV.

## Phase 4 — Model improvement

Status: future research.

- Backtest projection accuracy by market and position.
- Calibrate market coefficients from historical game logs.
- Explore a market-by-position matrix.
- Add player-specific volatility only when sample size is sufficient.
- Measure calibration, bias, and closing-line performance rather than judging the model from isolated bets.
- Preserve the current simple model as an understandable baseline.

## Phase 5 — Reporting and bankroll insight

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

1. Implement Phase 2C.1 reliable identities using nflverse-compatible season, week, game, team, and player fields.
2. Preserve the completed provider probes as isolated diagnostics and fixtures.
3. Implement preview-only result checking in Phase 2C.2.
4. Test it through real NFL weeks before enabling any automatic settlement.
5. Begin Phase 3A manual parlay evaluation.
6. Add parlay tracking by reusing the Phase 2C result engine.
7. Treat correlation and player-specific modeling as later evidence-driven improvements.

## Product safety principles

- The app assists decisions; it does not place wagers.
- Model EV is an estimate, not guaranteed value.
- No automatic financial-history change without an exact match and an audit record.
- No paid service, publication, or destructive data change without explicit approval.
- Build in meaningful, testable stages and pause for user feedback between stages.
