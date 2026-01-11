"""Data source adapters for the pipeline."""

from app.data_pipeline.adapters.base import (
    DataSourceAdapter,
    DataSourceType,
    ImportResult,
    RawEvent,
    RawFight,
    RawFighter,
)
from app.data_pipeline.adapters.espn import ESPNAdapter
from app.data_pipeline.adapters.kaggle import KaggleAdapter
from app.data_pipeline.adapters.ufc import UFCAdapter

__all__ = [
    "DataSourceAdapter",
    "DataSourceType",
    "ESPNAdapter",
    "ImportResult",
    "KaggleAdapter",
    "RawEvent",
    "RawFight",
    "RawFighter",
    "UFCAdapter",
]
