# QB–WR research: first data table

This first step produces a descriptive table from saved projections and nflverse
results. It does not calculate SGP probabilities, correlation adjustments or EV.

## Generate the report

From the project directory:

```powershell
python -m scripts.sgp_research_report --season 2026 --week 1 --refresh
```

Omit `--refresh` to reuse cached sources. Each run creates a new dated directory
under `data/research/`, containing a readable `report.html` and detailed
`report.json`. These local files are excluded from Git by the existing data rule.
Refreshing updates public nflverse caches; imports and betting records are unchanged.

## How to read it

- Each row pairs a projected QB's passing yards with a same-team WR's receiving yards.
- Each leg uses the latest compatible import strictly before its scheduled kickoff.
- Results require an exact normalized player/team/opponent match and a regular-season
  game with both final scores present in the schedule. Missing player results are
  not interpreted as zero.
- Difference is actual minus projection; it is not an Over/Under betting outcome.
- The table retains import timestamps and the JSON retains snapshot IDs and labels.
- Zero projections and multiple QBs with pass attempts are flagged, not silently
  removed. Multiple passers may reflect many situations and do not establish injury.
- Pairs sharing a QB or game are related observations. Future uncertainty estimates
  must account for that relationship.
- Coverage in the metadata describes all supported Phase 5 markets through the
  requested week; the visible pair table covers only the requested week.

The first generated Week 1 report contains 140 matched pairs, 30 teams and 15 games.
It flags 18 pairs for multiple QB passers and two for zero projections. These counts
describe this source snapshot; later corrections and source updates may change them.

## Next research milestone

Review data coverage and flagged cases, then accumulate subsequent weeks using the
same rules. A future experiment should test whether a simple dependence model
improves joint probability estimates on later games compared with multiplying the
same marginal probabilities. Exact sportsbook thresholds and quotes are required
for a subsequent evaluation of betting prices.
