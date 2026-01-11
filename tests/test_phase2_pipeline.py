"""Phase 2 integration tests for the data pipeline."""

import asyncio
from pathlib import Path

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.data_pipeline.adapters import KaggleAdapter
from app.data_pipeline.import_service import ImportService
from app.data_pipeline.snapshot_calculator import SnapshotCalculator
from app.data_pipeline.transformers import (
    Deduplicator,
    FighterTransformer,
    FightTransformer,
    normalize_name,
)
from app.db.models import Fight, FighterSnapshot

# Test fixtures path
FIXTURES_PATH = Path(__file__).parent / "fixtures"


class TestTransformers:
    """Test data transformers."""

    def test_normalize_name(self):
        """Test name normalization."""
        assert normalize_name("Conor McGregor") == "conor mcgregor"
        assert normalize_name("  DUSTIN POIRIER  ") == "dustin poirier"
        assert normalize_name("José Aldo") == "jose aldo"
        assert normalize_name("") == ""

    def test_fighter_validation(self):
        """Test fighter validation."""
        from app.data_pipeline.adapters.base import RawFighter

        # Valid fighter
        fighter = RawFighter(
            first_name="Conor",
            last_name="McGregor",
            height_cm=175.0,
            reach_cm=188.0,
        )
        result = FighterTransformer.validate(fighter)
        assert result.is_valid

        # Invalid fighter (no name)
        fighter = RawFighter(first_name="", last_name="")
        result = FighterTransformer.validate(fighter)
        assert not result.is_valid

    def test_fight_validation(self):
        """Test fight validation."""
        from app.data_pipeline.adapters.base import RawFight

        # Valid fight
        fight = RawFight(
            fighter1_name="Conor McGregor",
            fighter2_name="Dustin Poirier",
            weight_class="Lightweight",
        )
        result = FightTransformer.validate(fight)
        assert result.is_valid

        # Invalid fight (same fighter)
        fight = RawFight(
            fighter1_name="Conor McGregor",
            fighter2_name="Conor McGregor",
            weight_class="Lightweight",
        )
        result = FightTransformer.validate(fight)
        assert not result.is_valid

    def test_deduplicator(self):
        """Test fighter deduplication."""
        from app.data_pipeline.adapters.base import RawFighter

        fighters = [
            RawFighter(first_name="Conor", last_name="McGregor"),
            RawFighter(first_name="Dustin", last_name="Poirier"),
            RawFighter(first_name="Conor", last_name="Mcgregor"),  # Duplicate
        ]

        dedup = Deduplicator(similarity_threshold=0.85)
        result = dedup.deduplicate_fighters(fighters)
        assert len(result) == 2  # Should remove duplicate


class TestKaggleAdapter:
    """Test Kaggle CSV adapter."""

    @pytest.fixture
    def adapter(self):
        """Create Kaggle adapter with test fixtures."""
        return KaggleAdapter(
            data_dir=FIXTURES_PATH,
            fights_file="sample_fights.csv",
        )

    @pytest.mark.asyncio
    async def test_health_check(self, adapter):
        """Test adapter health check."""
        assert await adapter.health_check()

    @pytest.mark.asyncio
    async def test_fetch_fighters(self, adapter):
        """Test fetching fighters from CSV."""
        fighters = await adapter.fetch_fighters()
        assert len(fighters) > 0

        # Check specific fighters exist
        names = [f"{f.first_name} {f.last_name}".lower() for f in fighters]
        assert "conor mcgregor" in names
        assert "dustin poirier" in names
        assert "khabib nurmagomedov" in names

    @pytest.mark.asyncio
    async def test_fetch_events(self, adapter):
        """Test fetching events from CSV."""
        events = await adapter.fetch_events()
        assert len(events) > 0

        # Check specific events exist
        event_names = [e.name for e in events]
        assert any("UFC 264" in name for name in event_names)
        assert any("UFC 254" in name for name in event_names)

    @pytest.mark.asyncio
    async def test_fetch_fights(self, adapter):
        """Test fetching fights from CSV."""
        fights = await adapter.fetch_fights()
        assert len(fights) == 6  # We have 6 fights in sample

        # Check fight data
        fight = fights[0]
        assert fight.fighter1_name
        assert fight.fighter2_name
        assert fight.weight_class
        assert fight.event_name


@pytest.mark.asyncio
class TestImportPipeline:
    """Test full import pipeline with database."""

    @pytest.fixture
    async def db_session(self):
        """Create test database session."""
        engine = create_async_engine(
            str(settings.database_url),
            echo=False,
        )
        async_session = sessionmaker(
            engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )

        async with async_session() as session:
            yield session

        await engine.dispose()

    async def test_full_import(self, db_session):
        """Test importing sample data into database."""
        # Create adapter
        adapter = KaggleAdapter(
            data_dir=FIXTURES_PATH,
            fights_file="sample_fights.csv",
        )

        # Run import
        import_service = ImportService(db_session)
        result = await import_service.run_import(adapter)

        # Check results
        assert result.status == "completed"
        assert result.fighters_created > 0
        assert result.events_created > 0
        assert result.fights_created > 0

        print("\nImport Results:")
        print(f"  Fighters: {result.fighters_created} created")
        print(f"  Events: {result.events_created} created")
        print(f"  Fights: {result.fights_created} created")

        if result.errors:
            print(f"  Errors: {len(result.errors)}")
            for error in result.errors[:5]:
                print(f"    - {error}")

    async def test_snapshot_calculation(self, db_session):
        """Test snapshot calculation after import."""
        # First check if there are fights
        result = await db_session.execute(select(Fight))
        fights = result.scalars().all()

        if not fights:
            pytest.skip("No fights in database - run import first")

        # Calculate snapshots
        calculator = SnapshotCalculator(db_session)
        stats = await calculator.calculate_all_snapshots()

        print("\nSnapshot Results:")
        print(f"  Fights processed: {stats['fights_processed']}")
        print(f"  Snapshots created: {stats['snapshots_created']}")

        # Verify snapshots exist
        result = await db_session.execute(select(FighterSnapshot))
        snapshots = result.scalars().all()
        assert len(snapshots) > 0


def run_tests():
    """Run tests programmatically."""
    print("=" * 60)
    print("Phase 2 Pipeline Tests")
    print("=" * 60)

    # Test transformers
    print("\n1. Testing Transformers...")
    tests = TestTransformers()
    tests.test_normalize_name()
    print("   ✓ normalize_name works")
    tests.test_fighter_validation()
    print("   ✓ fighter validation works")
    tests.test_fight_validation()
    print("   ✓ fight validation works")
    tests.test_deduplicator()
    print("   ✓ deduplicator works")

    # Test Kaggle adapter
    print("\n2. Testing Kaggle Adapter...")
    adapter = KaggleAdapter(
        data_dir=FIXTURES_PATH,
        fights_file="sample_fights.csv",
    )

    async def test_adapter():
        assert await adapter.health_check()
        print("   ✓ health check passes")

        fighters = await adapter.fetch_fighters()
        print(f"   ✓ fetched {len(fighters)} fighters")

        events = await adapter.fetch_events()
        print(f"   ✓ fetched {len(events)} events")

        fights = await adapter.fetch_fights()
        print(f"   ✓ fetched {len(fights)} fights")

        return fighters, events, fights

    fighters, events, fights = asyncio.run(test_adapter())

    # Test full import
    print("\n3. Testing Full Import Pipeline...")

    async def test_import():
        engine = create_async_engine(str(settings.database_url), echo=False)
        async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

        async with async_session() as session:
            # Run import
            import_service = ImportService(session)
            result = await import_service.run_import(adapter)

            print(f"   ✓ import completed: {result.status}")
            print(f"     - Fighters created: {result.fighters_created}")
            print(f"     - Events created: {result.events_created}")
            print(f"     - Fights created: {result.fights_created}")

            if result.errors:
                print(f"     - Errors: {len(result.errors)}")

            # Test snapshot calculation
            print("\n4. Testing Snapshot Calculation...")
            calculator = SnapshotCalculator(session)
            stats = await calculator.calculate_all_snapshots()
            print(f"   ✓ snapshots created: {stats['snapshots_created']}")

            # Verify data in database
            fighters_count = await session.execute(text("SELECT COUNT(*) FROM fighters"))
            events_count = await session.execute(text("SELECT COUNT(*) FROM events"))
            fights_count = await session.execute(text("SELECT COUNT(*) FROM fights"))
            snapshots_count = await session.execute(text("SELECT COUNT(*) FROM fighter_snapshots"))

            print("\n5. Database Verification...")
            print(f"   ✓ Fighters in DB: {fighters_count.scalar()}")
            print(f"   ✓ Events in DB: {events_count.scalar()}")
            print(f"   ✓ Fights in DB: {fights_count.scalar()}")
            print(f"   ✓ Snapshots in DB: {snapshots_count.scalar()}")

        await engine.dispose()

    asyncio.run(test_import())

    print("\n" + "=" * 60)
    print("All Phase 2 tests passed!")
    print("=" * 60)


if __name__ == "__main__":
    run_tests()
