# Project: NFL +EV Betting Application (Bet365 Canada vs. Sharp Devig & FantasyPoints)

## Architecture

The NFL +EV Betting Application is designed with a clean decoupled architecture separating pure domain logic, statistical modeling, data normalization, state caching, background polling, and FastAPI presentation:

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                                 FastAPI Web Dashboard                                  │
│  - Modern Interactive UI (Tailwind CSS, Chart.js, Vanilla ES6 Modules)                 │
│  - Real-Time Multi-Column Sortable EV+ Data Table & Instant Search                     │
│  - Prop Breakdown Modal / Drawer (Raw Line, Devigged Fair Odds, PDF Curve, EV/Kelly)   │
│  - Interactive CSV & Clipboard Paste Ingest Zone                                       │
└─────────────────────────────────────────┬──────────────────────────────────────────────┘
                                          │ REST / SSE Endpoints
┌─────────────────────────────────────────▼──────────────────────────────────────────────┐
│                                FastAPI Backend Layer                                   │
│  - `app/api/routes.py`: /opportunities, /upload/projections, /upload/odds, /settings   │
│  - `app/services/poller.py`: Background poller with rate limit backoff                 │
│  - `app/db/cache.py`: Thread-Safe In-Memory Cache (sub-5ms multi-index filtering)      │
└─────────────────────────────────────────┬──────────────────────────────────────────────┘
                                          │
┌─────────────────────────────────────────▼──────────────────────────────────────────────┐
│                                Core Processing Engines                                 │
│  1. `app/core/devig.py`: Devigging (Multiplicative, Power/Shin, Additive, Juice)       │
│  2. `app/core/distributions.py`: Continuous (Log-Normal/Normal) & Discrete (P/NegBin)  │
│  3. `app/core/ev.py`: Dual-Edge Tri-Factor EV & Push-Adjusted Fractional Kelly Sizing  │
│  4. `app/core/normalizer.py`: 5-Step Player Fuzzy Matcher & 32-Team Canonical Mapper   │
└─────────────────────────────────────────┬──────────────────────────────────────────────┘
                                          │
┌─────────────────────────────────────────▼──────────────────────────────────────────────┐
│                           Pluggable Ingestion Adapters                                 │
│  - `app/adapters/oddspapi_adapter.py`: OddsPapi v4 Live Polling Adapter                │
│  - `app/adapters/csv_odds_adapter.py`: Offline CSV/JSON/Clipboard Odds Ingestion        │
│  - `app/adapters/fantasypoints_adapter.py`: FantasyPoints Multi-Format Ingest Engine   │
└────────────────────────────────────────────────────────────────────────────────────────┘
```

## Feature Inventory

| # | Feature | Description | Milestone | Source |
|---|---------|-------------|-----------|--------|
| 1 | Pydantic v2 Core Schemas | Type-safe data models for `OddsValue`, `Player`, `Event`, `MarketOffer`, `PlayerProjection`, `MatchedEVOpportunity` | M1 | R1 |
| 2 | NFL Player Prop & Core Market Definitions | Support 7 player prop markets (Pass Yds/TDs/Ints, Rush Yds, Rec Yds/Recs, Anytime TD) + 3 core markets (Moneyline, Spreads, Totals) | M1 | R1 |
| 3 | Player Name Normalization & Nickname Matching | 5-step cleaning (Unicode NFKD, suffix stripping Jr/II/III, punctuation, 25+ nickname alias mapping, RapidFuzz) | M1 | R1, AC |
| 4 | Canonical Team Abbreviation Normalization | 32-team canonical mapping handling variants (KAN/KC, WSH/WAS, LVR/LV, TAM/TB, NOR/NO) | M1 | R1, AC |
| 5 | Pluggable Odds Ingestion Pipeline | Base adapter interface with live API poller (OddsPapi v4) and CSV/JSON/Clipboard fallback parsing | M1 | R1, AC |
| 6 | Odds Conversion & Overround Utilities | Exact conversion between American, Decimal, Implied Probability, and Juice/Overround calculation | M2 | R2 |
| 7 | Multiplicative (Proportional) Devigging | Proportional margin removal for 2-way and multi-way markets | M2 | R2, AC |
| 8 | Additive (Equal Margin) Devigging | Equal margin subtraction across outcomes | M2 | R2, AC |
| 9 | Power & Shin Devigging Engine | Exact Shin solver (Newton-Raphson for informed trader z) and Power devigging correcting favorite-longshot bias | M2 | R2, AC |
| 10 | FantasyPoints Ingestion Engine | Multi-format ingest (CSV, Excel, clipboard paste) with delimiter auto-detection and header synonym resolution | M3 | R3, AC |
| 11 | Continuous Yardage Distribution Modeling | Log-Normal and Calibrated Normal PDF/CDF models with positional CV parameters (QB, RB, WR, TE) | M3 | R3, AC |
| 12 | Discrete Count Distribution Modeling | Poisson and Negative Binomial (overdispersion parameter $\alpha$) models for TDs, Receptions, INTs | M3 | R3, AC |
| 13 | Continuity Correction & Push Probability Calculation | Exact probability integration for integer lines with push refunds ($P(\text{Over}), P(\text{Under}), P(\text{Push})$) | M3 | R3 |
| 14 | Dual-Edge EV Calculation Engine | Compute Market-Implied EV, Model-Implied EV, and Blended Consensus Score with push adjustment | M4 | R4, AC |
| 15 | Fractional Kelly Criterion Bet Sizing | Push-adjusted Kelly formula ($f^* = \frac{\text{EV}}{D - 1} \times \kappa$) with bankroll parameters, min stake, and max caps | M4 | R4, AC |
| 16 | FastAPI Backend & REST API | High-performance async REST API for opportunities, filters, uploads, settings, and health | M5 | R5, AC |
| 17 | Thread-Safe In-Memory State Cache | Fast in-memory state store with multi-index query filtering (sub-5ms response) and background refresh | M5 | R5 |
| 18 | Interactive Modern Web Dashboard UI | Dense financial-grade data table, search, multi-column sort, market filter pills, EV threshold slider, CSV export | M5 | R5, AC |
| 19 | Interactive Upload & Clipboard Paste Zone | Drag-and-drop / file picker and text paste modal for instant recalculation of FantasyPoints projections & odds snapshots | M5 | R5, AC |
| 20 | Prop Breakdown Modal / Drawer | Detailed modal displaying raw Bet365 line, sharp reference line, devigged true probability, Chart.js PDF curve, and step-by-step math breakdown | M5 | R5 |
| 21 | Comprehensive Opaque-Box E2E Test Suite | 4-Tier requirement-driven test suite (Feature Coverage, Boundary/Corner, Pairwise Combinations, Real-World Workloads) | E2E Track | AC |
| 22 | Adversarial Coverage Hardening (Tier 5) | White-box stress-testing, edge-case hardening, and test gap elimination | Final Milestone | AC |

## Milestones

| # | Name | Scope | Dependencies | Status |
|---|------|-------|-------------|--------|
| M1 | Core Domain Models, Normalization & Ingestion Adapters | Pydantic v2 models, player/team normalizer, pluggable odds adapters, fallback parsers | none | IN_PROGRESS |
| M2 | Quantitative Devigging & True Probability Engine | Odds conversions, Multiplicative, Additive, Power, and Shin devigging algorithms with numerical solvers | M1 | DONE (73/73 tests pass, Gate PASS) |
| M3 | FantasyPoints Ingestion & Statistical Distribution Engine | FantasyPoints file/paste ingest, Log-Normal/Normal yardage models, Poisson/NegBin count models, integer push mechanics | M1 | DONE (96/96 tests pass, Gate PASS) |
| M4 | Dual-Edge EV+ Engine & Fractional Kelly Sizing | Market-implied EV, Model-implied EV, Blended scoring, push-adjusted Kelly bet sizing with bankroll caps | M2, M3 | IN_PROGRESS |
| M5 | FastAPI Backend, Modern Web UI & Interactive Components | FastAPI application, state cache, modern dashboard UI, interactive upload/paste zone, Prop Breakdown modal/drawer | M1, M2, M3, M4 | PLANNED |
| E2E | E2E Testing Track: Opaque-Box Test Suite & Runner | Design & build comprehensive 4-Tier test suite (Features, Boundaries, Combinations, Real-World) and publish `TEST_READY.md` | none | IN_PROGRESS |
| M6 | Final Milestone: 100% E2E Test Pass & Adversarial Hardening | Verify against `TEST_READY.md` (Tiers 1-4) and execute Tier 5 Adversarial Coverage Hardening | M5, E2E | PLANNED |

## Interface Contracts

### `app.core.normalizer`
```python
class PlayerNameNormalizer:
    @staticmethod
    def clean_name(raw_name: str) -> str: ...
    @staticmethod
    def match_player(target_name: str, candidate_pool: list[str], position: str | None = None, team: str | None = None, threshold: float = 85.0) -> str | None: ...

class TeamNormalizer:
    @staticmethod
    def canonical_team(raw_team: str) -> str: ...
```

### `app.core.devig`
```python
class DevigMethod(str, Enum):
    MULTIPLICATIVE = "multiplicative"
    ADDITIVE = "additive"
    POWER = "power"
    SHIN = "shin"

class DevigResult(BaseModel):
    method: DevigMethod
    fair_implied_probabilities: list[float]
    fair_decimal_odds: list[float]
    fair_american_odds: list[int]
    overround: float
    raw_probabilities: list[float]
    z_parameter: float | None = None

class DevigEngine:
    @staticmethod
    def devig(decimal_odds: list[float], method: DevigMethod = DevigMethod.SHIN) -> DevigResult: ...
    @staticmethod
    def american_to_decimal(american: int) -> float: ...
    @staticmethod
    def decimal_to_american(decimal: float) -> int: ...
```

### `app.core.distributions`
```python
class DistributionType(str, Enum):
    LOG_NORMAL = "log_normal"
    CALIBRATED_NORMAL = "calibrated_normal"
    POISSON = "poisson"
    NEGATIVE_BINOMIAL = "negative_binomial"

class DistributionResult(BaseModel):
    prob_over: float
    prob_under: float
    prob_push: float
    conditional_prob_over: float
    conditional_prob_under: float
    fair_decimal_over: float
    fair_decimal_under: float
    distribution_type: DistributionType

class DistributionEngine:
    @staticmethod
    def evaluate_continuous_prop(projection_mean: float, line: float, position: str, stat_category: str, dist_type: DistributionType = DistributionType.LOG_NORMAL, cv_override: float | None = None) -> DistributionResult: ...
    @staticmethod
    def evaluate_discrete_prop(projection_mean: float, line: float, stat_category: str, dist_type: DistributionType = DistributionType.NEGATIVE_BINOMIAL, alpha_override: float | None = None) -> DistributionResult: ...
```

### `app.core.ev`
```python
class EVResult(BaseModel):
    market_implied_ev: float | None
    model_implied_ev: float | None
    blended_ev: float
    blended_win_prob: float
    quarter_kelly_fraction: float
    quarter_kelly_stake: float
    half_kelly_stake: float
    full_kelly_stake: float
    recommended_stake: float

class EVEngine:
    @staticmethod
    def calculate_ev(bet365_decimal: float, market_fair_prob: float | None, model_fair_prob: float | None, prob_push: float = 0.0, weight_market: float = 0.60, weight_model: float = 0.40, bankroll: float = 2000.0, kelly_fraction: float = 0.25, min_stake: float = 5.0, max_bankroll_pct: float = 0.05) -> EVResult: ...
```

### `app.db.cache`
```python
class InMemoryCache:
    async def get_opportunities(self, market_type: str | None = None, min_ev: float = 0.0, search: str | None = None, sort_by: str = "blended_ev", sort_desc: bool = True) -> list[MatchedEVOpportunity]: ...
    async def update_odds(self, offers: list[MarketOffer]) -> None: ...
    async def update_projections(self, projections: list[PlayerProjection]) -> None: ...
    async def recalculate(self) -> None: ...
```

## Code Layout

```
c:/Users/victo/OneDrive/Desktop/Betting app/
├── app/
│   ├── __init__.py
│   ├── main.py                     # FastAPI app factory, lifespan, routing
│   ├── config.py                   # App configuration & settings
│   ├── schemas/
│   │   ├── __init__.py
│   │   ├── odds.py                 # OddsValue, MarketOffer, Bookmaker, Event
│   │   ├── projections.py          # PlayerProjection, StatCategory
│   │   └── ev.py                   # MatchedEVOpportunity, EVResult, PropBreakdown
│   ├── core/
│   │   ├── __init__.py
│   │   ├── normalizer.py           # Player & team normalizers, fuzzy matching
│   │   ├── devig.py                # Multiplicative, Additive, Power, Shin devigging
│   │   ├── distributions.py        # Log-Normal, Normal, Poisson, NegBin modeling
│   │   └── ev.py                   # EV engine & Fractional Kelly bet sizing
│   ├── adapters/
│   │   ├── __init__.py
│   │   ├── base.py                 # BaseOddsAdapter, BaseProjectionAdapter
│   │   ├── oddspapi_adapter.py     # Official OddsPapi NFL polling adapter
│   │   ├── the_odds_api.py         # Legacy snapshot/parser compatibility
│   │   ├── csv_odds_adapter.py     # Offline CSV/JSON/Clipboard odds adapter
│   │   └── fantasypoints.py        # FantasyPoints CSV/Excel/Paste ingest engine
│   ├── db/
│   │   ├── __init__.py
│   │   └── cache.py                # Thread-safe in-memory state cache
│   ├── services/
│   │   ├── __init__.py
│   │   ├── odds_service.py         # Ingestion orchestration & matching
│   │   └── poller.py               # Background poller with backoff
│   ├── api/
│   │   ├── __init__.py
│   │   └── routes.py               # REST API endpoints
│   └── static/
│       ├── index.html              # Modern interactive dashboard UI
│       ├── app.js                  # Frontend client logic & chart rendering
│       └── styles.css              # Custom styling & Tailwind configuration
├── tests/
│   ├── __init__.py
│   ├── unit/
│   │   ├── test_normalizer.py
│   │   ├── test_devig.py
│   │   ├── test_distributions.py
│   │   ├── test_ev_kelly.py
│   │   └── test_adapters.py
│   ├── integration/
│   │   ├── test_api_routes.py
│   │   └── test_cache_recalc.py
│   └── e2e/
│       ├── test_runner.py
│       ├── tier1_feature_coverage.py
│       ├── tier2_boundary_corner.py
│       ├── tier3_pairwise_combinations.py
│       └── tier4_real_world_workloads.py
├── sample_data/
│   ├── fantasypoints_sample.csv
│   ├── odds_snapshot_sample.json
│   └── odds_sample.csv
├── requirements.txt
├── run.py
├── PROJECT.md
└── ORIGINAL_REQUEST.md
```
