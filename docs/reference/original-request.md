# Original User Request

## 2026-08-15T00:52:02Z

# NFL +EV Betting Application (Bet365 Canada vs. Sharp Devig & FantasyPoints)

An NFL Expected Value (+EV) betting application specifically tailored for Bet365 Canada (Quebec / Global platform) player props and core lines. The system compares Bet365 odds against sharp devigged benchmarks (e.g. Pinnacle, Circa) and FantasyPoints.com statistical player projections to identify profitable market discrepancies and calculate optimal stake sizing.

Working directory: c:/Users/victo/OneDrive/Desktop/Betting app
Integrity mode: development

## Requirements

### R1. Multi-Source Odds Ingestion & Pluggable Adapters
- Implement a flexible odds ingestion pipeline supporting both automated API polling (e.g., OddsPapi, SportsGameOdds, or configurable REST endpoints) and manual file/clipboard fallback (CSV, JSON, pasted table text).
- Support standard NFL Player Prop markets (Passing Yards, Passing TDs, Rushing Yards, Receiving Yards, Receptions, Anytime TD, Interceptions) and secondary core markets (Moneyline, Point Spreads, Game Totals).
- Clean and normalize market terminology, player names, and team abbreviations across books.

### R2. Quantitative Devigging & True Probability Engine
- Implement standard quantitative devigging algorithms to calculate vig-free fair probabilities from sharp benchmark odds (Pinnacle/Circa):
  - Multiplicative (Proportional) devigging
  - Power / Shin devigging (accounting for favorite-longshot bias on high-odds props)
  - Additive (Equal Margin) devigging
- Expose fair decimal/American odds, implied probabilities, and overround (juice percentage).

### R3. FantasyPoints.com Projections Ingest & Distribution Modeling
- Provide an ingest workflow for FantasyPoints.com weekly NFL projections (CSV/Excel upload and table paste).
- Implement statistical probability density functions (PDF/CDF) to convert continuous point projections into discrete over/under probabilities:
  - Log-Normal / Calibrated Normal distributions for yardage props (Passing/Rushing/Receiving Yards) with configurable positional variance.
  - Poisson / Negative Binomial distributions for discrete count props (Anytime Touchdowns, Receptions, Interceptions).

### R4. Dual-Edge EV+ Engine & Bet Sizing
- Calculate Expected Value (EV%) for every available Bet365 line against:
  1. Market-Implied Fair Odds (Sharp devigged benchmark)
  2. Model-Implied Fair Odds (FantasyPoints projection distribution)
  3. Consensus / Blended Signal score
- Compute recommended bet sizes using Fractional Kelly Criterion (e.g., Full, Half, Quarter Kelly) with user-configurable bankroll parameters.

### R5. Interactive Python Web Dashboard
- Build a Python web application (FastAPI backend with a fast, modern interactive web UI).
- Provide real-time data table filtering, sorting (by EV%, Edge, League, Prop Market, Game, Book), search bar, and CSV export.
- Include an interactive CSV upload / paste zone for instant updates of FantasyPoints projections and offline odds snapshots.
- Provide a detailed "Prop Breakdown" modal or drawer showing the raw Bet365 line, sharp reference line, devigged true probability, projection distribution curve, and EV calculations.

## Acceptance Criteria

### Data Ingestion & Normalization
- [ ] Ingestion adapters successfully parse and normalize NFL player props from sample API JSON payloads and CSV uploads.
- [ ] Player name fuzzy matching handles variations (e.g. "Gabe Davis" vs "Gabriel Davis", "Patrick Mahomes II" vs "Patrick Mahomes") and matches player records to corresponding lines.

### Devigging & Mathematical Accuracy
- [ ] Devigging algorithms (Multiplicative, Power/Shin, Additive) accurately compute vig-free probabilities summing to 1.0 (100%) within a tolerance of 0.0001.
- [ ] Projection distribution models accurately calculate over/under probabilities from projection mean values.
- [ ] EV% formulas correctly evaluate: `EV = (Implied_Prob * Decimal_Odds) - 1`.

### Web Dashboard & Usability
- [ ] Web application runs locally on `http://localhost:8000` (or specified port) with fast response times.
- [ ] Dashboard displays an EV+ table with clear indicators for Bet365 line, Sharp benchmark, Fair line, EV%, and Kelly stake.
- [ ] Users can filter by prop market type (Passing, Rushing, Receiving, TDs, Core Lines) and set minimum EV% thresholds.
- [ ] FantasyPoints CSV files can be uploaded directly via the UI, immediately recalculating model-based EV edges.

### Verification & Testing
- [ ] Automated unit test suite (`pytest`) verifies devigging math, distribution calculations, name normalization, and EV computations.
