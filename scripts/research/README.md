# Research tools

These tools read saved app records. They do not settle bets or change live model settings. Run Python module commands from the project root. Node tools resolve data relative to their own location and can also run from another working directory.

| Tool | Scope | Command from project root |
| --- | --- | --- |
| Weekly process calculation | One week, currently season 2026 | `node scripts/research/weekly_process_audit.cjs 3 --save` |
| Straight-bet EV observation | Fixed 2026 Weeks 1–3; not a later-week report | `node scripts/research/ev_observation_weeks01_03.cjs --save` |
| Parlay construction observation | Cumulative through requested week/season | `node scripts/research/parlay_observation.cjs 3 2026 --save` |
| QB–WR table | One requested week | `python -m scripts.research.sgp_research_report --season 2026 --week 3` |
| Bulk participation source probe | Through requested week; validation only | `python -m scripts.research.bulk_participation_probe --season 2026 --through-week 3` |

Node tools print JSON; `--save` additionally creates a new dated `audit.json` under `research/SEASON/betting-process/reports/`. The path is printed separately. Omit `--save` for no report-file writes. The JSON is calculation support, not the human-readable weekly review.

The bulk probe downloads public team totals, reads saved player/schedule/snap data, and writes dated `report.json` plus `team-source.json` under `research/SEASON/calibration/reports/`. It does not overwrite app caches, modify the participation preview, or accept candidates into main metrics. It requires saved schedule/player-stat data; run the normal report first if those caches are absent.

SGP creates a dated folder under `research/SEASON/sgp-correlation/reports/`, keeping `report.html` and `report.json` together. `--refresh` explicitly refreshes provider caches; otherwise it reuses available cached sources. The old Python entry point remains as a compatibility wrapper.

Existing SGP runs under `data/research/` are historical outputs, preserved in place and linked from the research home. No existing report is overwritten. Readable weekly reviews and observations are written separately, following [the review workflow](../../docs/research-plans/betting-process.md). Keep the [research home](../../research/README.md) updated after a new report.
