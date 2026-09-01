"""
app.adapters: Ingestion adapters for live sportsbooks, APIs, CSVs, and projections.
"""

from app.adapters.base import BaseOddsAdapter, BaseProjectionAdapter
from app.adapters.the_odds_api import OddsAPIQuotaExceededError, TheOddsAPIAdapter
from app.adapters.oddspapi_adapter import OddsPapiAdapter
from app.adapters.csv_odds_adapter import CSVOddsAdapter

__all__ = [
    "BaseOddsAdapter",
    "BaseProjectionAdapter",
    "TheOddsAPIAdapter",
    "OddsPapiAdapter",
    "OddsAPIQuotaExceededError",
    "CSVOddsAdapter",
]
