# PropLens research home

Start here for research findings. Plans describe the workflow; reports describe results; audits check whether the source data is usable; observations record hypotheses, not proven model improvements.

## Calibration — are projections and model probabilities accurate?

- [Plan and evidence gates](../docs/research-plans/calibration.md)
- Current mean-accuracy results: **in the app**, under Model research. This cleanup does not create a saved export or change report persistence.
- [Weeks 1–3 coverage audit](2026/calibration/data-quality/through-week-03-coverage-audit.md)
- [Participation review: batch 1](2026/calibration/data-quality/participation-review-batch-01.md)
- [Participation review: batch 2](2026/calibration/data-quality/participation-review-batch-02.md) — latest recovery checkpoint, September 30.

Status: descriptive measurement and data-quality investigation. Verified receiving zeros are preview-only; do not assume they have entered the main metrics. Next: validate repeatable final-stat recovery. No live-model adjustment.

## Betting process — how are our betting decisions performing?

- [Review workflow](../docs/research-plans/betting-process.md)
- [Week 1 review](2026/betting-process/weekly/week-01-process-review.md)
- [Week 2 review](2026/betting-process/weekly/week-02-process-review.md)
- [Week 3 review](2026/betting-process/weekly/week-03-process-review.md) — latest weekly review.
- [Through Week 3: EV observations](2026/betting-process/observations/through-week-03-ev-observations.md)
- [Through Week 3: parlay construction observations](2026/betting-process/observations/through-week-03-parlay-observations.md)

Status: descriptive decision/performance reviews, separate from model calibration. Next: a requested Week 4 review after settlement, with cumulative comparisons and timing limitations preserved.

Saved calculation files from the September 30 cleanup verification (not new written findings): [Week 3 process audit](2026/betting-process/reports/week-03_weekly-process-audit_20260930T204020646Z/audit.json), [through Week 3 EV audit](2026/betting-process/reports/through-week-03_ev-observation_20260930T204021010Z/audit.json), and [through Week 3 parlay audit](2026/betting-process/reports/through-week-03_parlay-observation_20260930T204021176Z/audit.json).

## SGP correlation — how do QB and WR outcomes move together?

- [Research workflow](../docs/research-plans/sgp-correlation.md)
- [Week 1 findings](2026/sgp-correlation/observations/week-01-sgp-findings.md)
- [Through Week 3 findings](2026/sgp-correlation/observations/through-week-03-sgp-findings.md) — latest written checkpoint.
- Generated tables: [Week 1](../data/research/sgp_2026_week1_20260915T031011808730Z/report.html), [Week 2](../data/research/sgp_2026_week2_20260922T174725946529Z/report.html), [Week 3](../data/research/sgp_2026_week3_20260930T023610164266Z/report.html).
- [Week 3 table regenerated to verify the new output location](2026/sgp-correlation/reports/week-03_20260930T204019132999Z/report.html) — September 30, saved-cache run; not a new interpretation or source refresh.

Status: descriptive QB–WR research, not correlated parlay EV. Next: accumulate later weeks and review coverage before testing a dependence model.

## Filing rules

- `week-03` means Week 3 alone; `through-week-03` means Weeks 1–3 cumulatively.
- Plans: `docs/research-plans/`. Human-readable findings: `research/SEASON/TOPIC/`.
- Calibration source-quality checks: `calibration/data-quality/`. Future saved accuracy reports: `calibration/reports/`.
- Betting-process reviews: `betting-process/weekly/`; cumulative hypotheses: `betting-process/observations/`.
- SGP findings: `sgp-correlation/observations/`. New generated HTML/JSON runs stay together under `sgp-correlation/reports/`. Historical runs remain under `data/research/`, linked above.
- Research generators now live under `scripts/research/`; see the [tool guide](../scripts/research/README.md). Optional saved betting-process calculation results go under `betting-process/reports/`, separate from written reviews and observations. No cache or saved app record was moved.
- Season reports remain local-only and excluded from Git. They are not backed up by a normal commit; preserve them in your existing folder backups.
- After each new report, update this index with its period, status, and next checkpoint. Do not overwrite dated generated runs.
