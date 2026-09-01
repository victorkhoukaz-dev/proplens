# NFL +EV Betting Application — E2E Test Suite & Infrastructure Specification

**Document Version**: 1.0.0  
**Target Environment**: Python 3.12+ (Standard Library & Pytest Compatible)  
**Execution Isolation**: 100% Offline / Zero External Network Egress  
**Workspace Root**: `c:/Users/victo/OneDrive/Desktop/Betting app`

---

## 1. Executive Summary & Test Infrastructure Overview

The NFL +EV Betting Application E2E Test Suite provides comprehensive, opaque-box, requirement-driven automated verification spanning Requirements R1 through R5 as specified in `ORIGINAL_REQUEST.md` and `PROJECT.md`.

```
┌────────────────────────────────────────────────────────────────────────┐
│                   CLI Test Runner (tests/e2e/test_runner.py)           │
│  Options: --tier 1,2,3,4,all | -v | --json-report | -x | -k | --color  │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
 ┌──────────────────────────────────▼──────────────────────────────────┐
 │                     4-Tier Verification Matrix                      │
 │  - Tier 1: Feature Coverage (F01–F20, ≥100 tests, ≥5 per feature)   │
 │  - Tier 2: Boundary & Corner Cases (Stress, Edge, Bounds, ≥100 tests)│
 │  - Tier 3: Pairwise Combinations (Cross-Engine Matrices, ≥20 tests) │
 │  - Tier 4: Real-World Workloads (16-Game Slate, E2E Journey, ≥10 t) │
 └──────────────────────────────────┬──────────────────────────────────┘
                                    │
 ┌──────────────────────────────────▼──────────────────────────────────┐
 │            Offline Isolation Harness & Fixtures (sample_data/)      │
 │  - fantasypoints_sample.csv: Multi-position weekly projections      │
 │  - odds_snapshot_sample.json: TheOddsAPI v4 multi-book snapshot     │
 │  - odds_sample.csv: Tabular offline sportsbook lines                │
 │  - Zero external API/network calls; microsecond in-memory execution │
 └─────────────────────────────────────────────────────────────────────┘
```

---

## 2. 4-Tier Test Architecture

### 2.1 Tier Breakdown & Scope

| Tier | Module | Primary Objective | Target Size |
|---|---|---|---|
| **Tier 1** | `tests/e2e/tier1_feature_coverage.py` | Complete nominal functional coverage of all 20 core features (F01–F20) | $\ge 100$ tests ($\ge 5$ / feature) |
| **Tier 2** | `tests/e2e/tier2_boundary_corner.py` | Boundary, singularity, extreme value, negative input, and fault resilience testing across all 20 features | $\ge 100$ tests |
| **Tier 3** | `tests/e2e/tier3_pairwise_combinations.py` | Systematic 2-way orthogonal cross-engine combinatorial verification | $\ge 20$ tests |
| **Tier 4** | `tests/e2e/tier4_real_world_workloads.py` | Full-scale 16-game weekly slates, multi-book live polling, FantasyPoints upload recalculation, and end-to-end user journeys | $\ge 10$ tests |

---

## 3. Sample Data Fixtures Specification

The test suite is powered by three deterministic offline fixtures located in `sample_data/`:

### 3.1 `sample_data/fantasypoints_sample.csv`
- **Format**: Standard CSV with header row.
- **Coverage**: 30+ NFL players across QBs, RBs, WRs, TEs from 8 NFL teams (KC, BAL, BUF, NYJ, PHI, DAL, SF, DET, MIA, HOU, SEA, ARI).
- **Columns**: `Player,Team,Opp,Pos,Pass Att,Pass Cmp,Pass Yds,Pass TD,Pass Int,Rush Att,Rush Yds,Rush TD,Targets,Rec,Rec Yds,Rec TD,Anytime TD,Fantasy Points`
- **Player Variations**: Includes generational suffixes (`Patrick Mahomes II`, `Kenneth Walker III`, `Marvin Harrison Jr.`), punctuation (`Ja'Marr Chase`, `A.J. Brown`), and nickname aliases (`Gabriel Davis`, `Marquise Brown`, `Chigoziem Okonkwo`).

### 3.2 `sample_data/odds_snapshot_sample.json`
- **Format**: JSON mirroring TheOddsAPI v4 live feed structure.
- **Events**: 4 NFL game events (KC vs BAL, BUF vs NYJ, PHI vs DAL, SF vs DET).
- **Bookmakers**: `bet365` (soft target), `pinnacle` (sharp benchmark), `circa` (sharp retail benchmark), `draftkings`, `fanduel`.
- **Markets**:
  - Core: `h2h` (Moneyline), `spreads` (Point Spreads), `totals` (Game Totals)
  - Props: `player_pass_yds`, `player_pass_tds`, `player_rush_yds`, `player_reception_yds`, `player_receptions`, `player_anytime_td`, `player_pass_interceptions`

### 3.3 `sample_data/odds_sample.csv`
- **Format**: Tabular offline CSV for upload/clipboard verification.
- **Columns**: `Sport,Event,Date,Bookmaker,Market,Player,Option,Line,Price_American,Price_Decimal`
- **Rows**: 50+ lines covering props and core game lines across multiple bookmakers.

---

## 4. Standalone CLI Runner (`tests/e2e/test_runner.py`)

### 4.1 CLI Command Line Interface & Flags

```powershell
python tests/e2e/test_runner.py [-h] [--tier {1,2,3,4,all}] [-v] [--json-report [FILE]] [-x] [-k PATTERN] [--color {auto,always,never}]
```

| Option | Short | Type / Choices | Default | Description |
|---|---|---|---|---|
| `--tier` | `-t` | `1,2,3,4,all` | `all` | Select one or more tiers (comma-separated, e.g. `1,2` or `all`) |
| `--verbose` | `-v` | flag | `False` | Show detailed individual test execution logs with millisecond timings |
| `--json-report` | `-j` | optional `[FILE]` | `test_report.json` | Generate structured machine-readable JSON execution report |
| `--fail-fast` | `-x` | flag | `False` | Immediately abort test execution upon encountering the first failure |
| `--filter` | `-k` | `str` | `None` | Filter test cases by substring or regex matching test method/class name |
| `--color` | | `auto,always,never`| `auto` | Control ANSI colorized terminal output |

### 4.2 Exit Code Contract
- **`0`**: All executed tests passed cleanly.
- **`1`**: One or more tests failed or raised an unexpected error.
- **`2`**: CLI argument parsing or test suite configuration error.

---

## 5. Verification Commands

```powershell
# 1. Run complete E2E test suite across all 4 tiers with verbose logging
python tests/e2e/test_runner.py --tier all -v

# 2. Run specific tiers
python tests/e2e/test_runner.py --tier 1
python tests/e2e/test_runner.py --tier 2
python tests/e2e/test_runner.py --tier 3
python tests/e2e/test_runner.py --tier 4

# 3. Generate JSON report
python tests/e2e/test_runner.py --tier all --json-report test_report.json

# 4. Filter tests by pattern
python tests/e2e/test_runner.py -k shin

# 5. Native pytest discovery
pytest tests/e2e/ -v
```
