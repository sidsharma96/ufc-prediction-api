"""Shared test fixtures for integration tests."""

import asyncio
import os
from datetime import date, timedelta
from typing import AsyncGenerator
from uuid import uuid4

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.db.models import Event, Fight, Fighter, FighterSnapshot
from app.db.session import get_db
from app.main import app


# Use PostgreSQL test database (same as dev but different db name)
TEST_DATABASE_URL = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://postgres:postgres@localhost:5433/ufc_predictions_test"
)


@pytest.fixture(scope="session")
def event_loop():
    """Create event loop for async tests."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="function")
async def test_engine():
    """Create test database engine."""
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(test_engine) -> AsyncGenerator[AsyncSession, None]:
    """Provide transactional database session."""
    async_session = sessionmaker(
        test_engine, class_=AsyncSession, expire_on_commit=False
    )
    async with async_session() as session:
        yield session
        await session.rollback()


@pytest_asyncio.fixture
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """Create async HTTP client with test database."""

    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test"
    ) as ac:
        yield ac

    app.dependency_overrides.clear()


# =============================================================================
# Test Data Factories
# =============================================================================

class FighterFactory:
    """Factory for creating test fighters."""

    @staticmethod
    async def create(
        db: AsyncSession,
        first_name: str = "Test",
        last_name: str = "Fighter",
        **kwargs
    ) -> Fighter:
        defaults = {
            "id": uuid4(),
            "first_name": first_name,
            "last_name": last_name,
            "weight_class": "Lightweight",
            "is_active": True,
            "nationality": "USA",
        }
        defaults.update(kwargs)
        fighter = Fighter(**defaults)
        db.add(fighter)
        await db.flush()
        return fighter


class EventFactory:
    """Factory for creating test events."""

    @staticmethod
    async def create(
        db: AsyncSession,
        name: str = "UFC Test Event",
        **kwargs
    ) -> Event:
        defaults = {
            "id": uuid4(),
            "name": name,
            "date": date.today() + timedelta(days=7),
            "venue": "Test Arena",
            "city": "Las Vegas",
            "country": "USA",
            "is_completed": False,
            "is_cancelled": False,
        }
        defaults.update(kwargs)
        event = Event(**defaults)
        db.add(event)
        await db.flush()
        return event


class FightFactory:
    """Factory for creating test fights."""

    @staticmethod
    async def create(
        db: AsyncSession,
        event: Event,
        fighter1: Fighter,
        fighter2: Fighter,
        **kwargs
    ) -> Fight:
        defaults = {
            "id": uuid4(),
            "event_id": event.id,
            "fighter1_id": fighter1.id,
            "fighter2_id": fighter2.id,
            "weight_class": "Lightweight",
            "status": "scheduled",
            "scheduled_rounds": 3,
        }
        defaults.update(kwargs)
        fight = Fight(**defaults)
        db.add(fight)
        await db.flush()
        return fight


class SnapshotFactory:
    """Factory for creating fighter snapshots."""

    @staticmethod
    async def create(
        db: AsyncSession,
        fighter: Fighter,
        fight: Fight,
        **kwargs
    ) -> FighterSnapshot:
        defaults = {
            "id": uuid4(),
            "fighter_id": fighter.id,
            "fight_id": fight.id,
            "snapshot_date": date.today(),
            "wins": 10,
            "losses": 2,
            "draws": 0,
            "no_contests": 0,
            "striking_accuracy": 50.0,
            "takedown_defense": 75.0,
        }
        defaults.update(kwargs)
        snapshot = FighterSnapshot(**defaults)
        db.add(snapshot)
        await db.flush()
        return snapshot


# =============================================================================
# Pre-built Fixtures
# =============================================================================

@pytest_asyncio.fixture
async def sample_fighters(db_session: AsyncSession) -> list[Fighter]:
    """Create sample fighters for testing."""
    fighters = [
        await FighterFactory.create(
            db_session, "Conor", "McGregor", nickname="The Notorious"
        ),
        await FighterFactory.create(
            db_session, "Dustin", "Poirier", nickname="The Diamond"
        ),
        await FighterFactory.create(
            db_session, "Khabib", "Nurmagomedov", nickname="The Eagle"
        ),
    ]
    await db_session.commit()
    return fighters


@pytest_asyncio.fixture
async def sample_event(db_session: AsyncSession) -> Event:
    """Create sample event for testing."""
    event = await EventFactory.create(db_session, name="UFC 300: Test Event")
    await db_session.commit()
    return event


@pytest_asyncio.fixture
async def sample_fight(
    db_session: AsyncSession,
    sample_event: Event,
    sample_fighters: list[Fighter]
) -> Fight:
    """Create sample fight with snapshots."""
    fight = await FightFactory.create(
        db_session,
        event=sample_event,
        fighter1=sample_fighters[0],
        fighter2=sample_fighters[1],
        is_main_event=True,
    )

    # Create snapshots for both fighters
    await SnapshotFactory.create(db_session, sample_fighters[0], fight)
    await SnapshotFactory.create(db_session, sample_fighters[1], fight)

    await db_session.commit()
    return fight


@pytest_asyncio.fixture
async def completed_fight(
    db_session: AsyncSession,
    sample_event: Event,
    sample_fighters: list[Fighter]
) -> Fight:
    """Create a completed fight for testing."""
    # Mark event as completed
    sample_event.is_completed = True

    fight = await FightFactory.create(
        db_session,
        event=sample_event,
        fighter1=sample_fighters[0],
        fighter2=sample_fighters[1],
        status="completed",
        winner_id=sample_fighters[0].id,
        result_method="KO/TKO",
        ending_round=2,
        ending_time="3:45",
    )

    # Create snapshots
    await SnapshotFactory.create(db_session, sample_fighters[0], fight, wins=15, losses=3)
    await SnapshotFactory.create(db_session, sample_fighters[1], fight, wins=12, losses=5)

    await db_session.commit()
    return fight
