# Phase 5 — Model Measurement and Calibration

## Purpose

Phase 5 measures the existing FantasyPoints + PropLens baseline before changing it. It does not alter live probabilities, volatility coefficients, past bets, parlays, or saved evaluation snapshots.

The first question is: **how accurate are the imported FantasyPoints projection means by market?**

## Weekly routine

| Timing | Victor | PropLens / Codex |
| --- | --- | --- |
| Now through Week 2 | Import every FantasyPoints release used, including Thursday/Sunday/Monday files and meaningful updates. Use descriptive labels. | Preserve timestamped snapshots; no live model change. |
| Tuesday after Week 2 | Confirm games are final and use normal bet result checks. | Run Phase 5.0 coverage and mean-accuracy report. |
| After Week 3 | Keep importing every release. | Refresh descriptive report: projection mean, actual, bias, MAE, RMSE, and largest misses. |
| After Week 4 | Review evidence with Codex. | Compare early findings across reports; label hypotheses only. |
| Weeks 5–8 | Maintain consistent imports. | Add probability calibration reporting for settled evaluated bets. |
| Earliest Week 9 gate | Review accumulated evidence. | Test one narrow candidate only if it passes the gates below. |
| Offseason | Preserve all local data. | Run full-season review and propose next-season changes. |

## Phase 5.0 — Current implementation

The read-only Mean Accuracy report uses every compatible player-market in saved FantasyPoints snapshots. It supports passing yards, rushing yards, receiving yards, and receptions.

For each player-market, it:

1. Matches team/opponent/week to an nflverse regular-season schedule record.
2. Uses the latest imported compatible snapshot before the verified game kickoff.
3. Matches final nflverse player statistics by normalized player name, team, opponent, season, and week.
4. Excludes missing or ambiguous matches rather than guessing or treating them as zero.

The report shows coverage, excluded-row reasons, average projection, average actual, bias (actual minus projection), MAE, RMSE, and the ten largest absolute errors. It never changes the live evaluator.

## Phase 5.1 — Projection mean accuracy

Initial reports group by market. Position splits should wait until each subgroup has enough observations to avoid noisy conclusions.

- **Bias:** whether actual results average above or below the mean projection.
- **MAE:** typical absolute miss size.
- **RMSE:** error measure that weighs very large misses more heavily.

## Phase 5.2 — Probability calibration

Keep these populations separate:

1. All imported projections: projection-mean accuracy.
2. Decision-time evaluated bets: model probability and EV performance.
3. Manual bets evaluated later: useful research, but not proof the model informed the original wager.

Later reports will include probability buckets, actual win rate versus predicted win rate, Brier score, EV-bucket results, sample sizes, and ROI/profit as supplementary evidence.

## Evidence gates before live changes

No live coefficient change is permitted until all of the following are true:

- Eight completed NFL weeks of clean imported data.
- At least 300 matched player-games in the affected market.
- At least 90% usable matching coverage, or a documented source limitation.
- A consistent issue across two consecutive reports.
- A chronological holdout test: choose the candidate using earlier weeks and test it on later unseen weeks.
- Better calibration/accuracy than the unchanged baseline without an obvious offsetting regression.

The first possible adjustment is market-wide only: a documented bias correction or a revised market volatility coefficient. Position matrices, player-specific adjustments, blends, and correlation are later research stages.

## Snapshot rule

For split slates and updates, the authoritative research snapshot is the **latest matching projection imported before that player’s scheduled kickoff**. Files imported after kickoff are preserved for audit but excluded from that game’s accuracy calculation.

## Future direction

1. Calibrate the uncertainty layer around FantasyPoints means.
2. Compare a permitted, independent projection source or blend against FantasyPoints-only.
3. Research an in-house projection model offline before it ever affects live evaluations.

Parlay correlation remains separate from Phase 5. It should only begin after the straight-prop baseline is measured and calibrated.
