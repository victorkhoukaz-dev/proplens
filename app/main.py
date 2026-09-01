"""
app.main: FastAPI server entrypoint and static asset serving.
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.adapters.csv_odds_adapter import CSVOddsAdapter
from app.adapters.fantasypoints import FantasyPointsAdapter
from app.api.routes import router
from app.db.cache import cache
from app.db.loaded_data_store import loaded_data_store
from app.db.projection_snapshot_store import projection_snapshot_store
from app.db.settings_store import settings_store
from app.services.ev_pipeline import pipeline_service

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = BASE_DIR / "static"
SAMPLE_DATA_DIR = BASE_DIR / "sample_data"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Auto-seed sample data on startup for immediate out-of-the-box interactivity.
    """
    logger.info("Initializing NFL +EV Betting Server...")

    # Restore settings before loading data so calculations use the saved values.
    saved_settings = settings_store.load()
    if saved_settings:
        cache.set_settings(**saved_settings)
        logger.info("Restored local settings (API key remains hidden from browser responses)")

    saved_data = loaded_data_store.load()
    library = projection_snapshot_store.list_summaries()
    active_snapshot_id = library["active_id"]
    restored_projections = False
    if active_snapshot_id:
        active_snapshot = projection_snapshot_store.get(str(active_snapshot_id))
        cache.replace_projections(active_snapshot.projections)
        restored_projections = True
        logger.info("Restored active projection set: %s", active_snapshot.label)
    elif saved_data and saved_data.projections:
        restored_projections = True
        cache.replace_projections(saved_data.projections)
        first = saved_data.projections[0]
        projection_snapshot_store.create(
            saved_data.projections,
            label=f"Restored projection set — {first.season} Week {first.week or 1}",
            source="Restored local data",
            season=first.season,
            week=first.week or 1,
        )
    restored_events = bool(saved_data and saved_data.events)
    if saved_data:
        if restored_events:
            cache.store_events(saved_data.events)
        logger.info(
            "Restored %d saved events and %d saved projections",
            len(saved_data.events),
            len(saved_data.projections),
        )
    
    # 1. Load FantasyPoints sample projections if available
    fp_path = SAMPLE_DATA_DIR / "fantasypoints_sample.csv"
    if not restored_projections and fp_path.exists():
        try:
            adapter = FantasyPointsAdapter()
            projs = adapter.parse_projections(fp_path.read_text(encoding="utf-8"))
            cache.store_projections(projs)
            logger.info("Auto-loaded %d sample player projections", len(projs))
        except Exception as e:
            logger.warning("Could not auto-load sample projections: %s", e)

    # 2. Load Odds snapshot sample if available
    odds_json = SAMPLE_DATA_DIR / "odds_snapshot_sample.json"
    odds_csv = SAMPLE_DATA_DIR / "odds_sample.csv"
    odds_adapter = CSVOddsAdapter()
    
    if restored_events:
        pass
    elif odds_json.exists():
        try:
            events = odds_adapter.parse_payload(odds_json.read_text(encoding="utf-8"))
            cache.store_events(events)
            logger.info("Auto-loaded %d sample events from JSON snapshot", len(events))
        except Exception as e:
            logger.warning("Could not auto-load sample odds snapshot: %s", e)
    elif odds_csv.exists():
        try:
            events = odds_adapter.parse_payload(odds_csv.read_text(encoding="utf-8"))
            cache.store_events(events)
            logger.info("Auto-loaded %d sample events from CSV", len(events))
        except Exception as e:
            logger.warning("Could not auto-load sample odds CSV: %s", e)

    # 3. Trigger initial pipeline calculation
    opps = pipeline_service.process_data()
    logger.info("Initial calculation complete: %d +EV opportunities loaded", len(opps))
    
    yield
    logger.info("Shutting down NFL +EV Betting Server...")


app = FastAPI(
    title="PropLens Manual NFL Prop Evaluator",
    description="A projection-backed manual evaluator for exact Bet365 NFL player-prop inputs.",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS middleware for local and client connections
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API endpoints
app.include_router(router)

# Mount static folder
if not STATIC_DIR.exists():
    STATIC_DIR.mkdir(parents=True, exist_ok=True)

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/", include_in_schema=False)
async def serve_index() -> FileResponse:
    index_file = STATIC_DIR / "index.html"
    if not index_file.exists():
        # Fallback response if UI not generated yet
        return FileResponse(index_file)
    return FileResponse(index_file)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=True)
