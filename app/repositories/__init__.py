"""Repository layer for data access.

All repositories are exported from this module:
    from app.repositories import FighterRepository, EventRepository
"""

from app.repositories.base import BaseRepository
from app.repositories.event import EventRepository
from app.repositories.fight import FightRepository
from app.repositories.fighter import FighterRepository
from app.repositories.prediction import SystemPredictionRepository

__all__ = [
    "BaseRepository",
    "EventRepository",
    "FightRepository",
    "FighterRepository",
    "SystemPredictionRepository",
]
