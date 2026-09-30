# Weekly betting-process review workflow

When the user asks to run a weekly betting-process review, include both the straight-bet positive-versus-negative EV observation and the parlay construction observation as standard parts of the report. This is an assistant-run report workflow, requested September 29–30, 2026.

## Standard scope

Read the settled tracker for the requested season/week and preserve all source records. Verify financial totals and source fingerprints. Review straights, markets/sides, funding/promotions, sizing/concentration, and decision context. Include negative original evaluations and later negative evaluations/refreshes separately, counting unique tickets and preserving timing uncertainty. Keep model calibration as a separate research task.

## Required straight-bet positive-versus-negative EV section

Show the requested week's results and the cumulative season-to-date comparison. Use one latest saved evaluation strictly before the matched game's kickoff per settled straight, including original evaluations, later evaluations, and projection refreshes. Exclude snapshots at/after kickoff and visibly count missing timing, game matches, unsupported markets, or missing evaluations. Never infer placement time from tracker-entry time or assume a saved evaluation proves it was viewed.

Keep anytime TD outside the main comparison and show it separately. For positive and negative EV, report ticket counts, wins/losses, win rate, stake, realized profit, and ROI, with market and week breakdowns. Keep cash and bonus funding separate; report when there are no eligible bonus straights. Unknown EV is not zero. Analyst-led bets remain in their applicable EV group while retaining source context.

Check whether the observation changes when using the first available pre-game evaluation or original evaluations only; show sign changes and materially different findings. Count each ticket once per comparison. Describe observed performance with sample-size and price/market differences where relevant; do not infer calibrated EV or a causal benefit from the outcome.

The initial reference is [through-week-03-ev-observations.md](../../research/2026/betting-process/observations/through-week-03-ev-observations.md), supported by `scripts/research/ev_observation_weeks01_03.cjs`. That script currently covers Weeks 1–3 of 2026; extend its scope for a future requested week before producing the cumulative comparison. Do not present its fixed baseline as later-week output. Commands and code paths in this workflow are relative to the project root.

## Required parlay construction section

Show both the requested week's construction results and the cumulative season-to-date results through that week. Compare winners and losers, and show cash-outs separately. Report:

- Source: self-built (`Me`), recorded analyst/named source, and unknown. Source is independent of timing/period: a ticket may be analyst-led and Q1, or self-built and live.
- Leg count, total effective decimal odds, and cash versus bonus funding. Include boost/Safety Net context where it explains results.
- Markets present and recurring combinations, including QB rushing with receiving yards.
- Same-game versus cross-game construction and team allocation (one per team, 2+1, 2+2, one-team tickets, etc.) where identities are complete.
- Over-only versus constructions containing unders; explicit live and Q1 labels.
- A short list of winning constructions and recurring losing groups, with counts and denominators, then themes to revisit next week.

Use descriptive wording. A pattern found among a few winners is an observation, not proof of an advantage. Compare against losing tickets too. Distinguish win rate from profitability, and retain cash/bonus accounting separately. Identify overlapping groups, source-label gaps, incomplete leg/game identity, different odds/funding, and concentration when these materially affect interpretation. Market presence does not prove that market caused a loss. Do not calculate parlay EV as part of this construction section.

Do not assume unlabelled older tickets were analyst-built or self-built. `Me` began in Week 3. Free-text rows may contain multiple legs, so use unknown actual leg count when needed. Include unknown tickets financially, but do not invent their construction. Explicit game context from descriptions may be discussed with attribution; distinguish it from structured identity.

## Calculation support and outputs

- Weekly financial audit: `node scripts/research/weekly_process_audit.cjs WEEK` (currently 2026).
- Cumulative parlay construction audit: `node scripts/research/parlay_observation.cjs WEEK SEASON`. Omitted arguments reproduce Weeks 1–3 of 2026. The audit includes settled wins, losses, and cash-outs; pending tickets are excluded. Use its per-week groups/records for the current-week comparison.
- Add `--save` to a calculation command to preserve its JSON in a new dated folder under `research/SEASON/betting-process/reports/`. This is calculation support, not a replacement for the written review. The EV observation tool is still explicitly limited to Weeks 1–3 of 2026.
- Save the weekly report under `research/SEASON/betting-process/weekly/week-NN-process-review.md`; save cumulative observations under `research/SEASON/betting-process/observations/through-week-NN-TOPIC-observations.md`. Update the research index after each requested review.

The user can simply ask for the weekly review. No manual Node commands or scheduled automation are required from the user. This workflow does not add an app button or change the evaluator.
