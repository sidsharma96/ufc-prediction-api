#!/usr/bin/env python3
"""Calculate point-in-time snapshots for all fights."""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.data_pipeline.snapshot_calculator import SnapshotCalculator
from app.db.session import AsyncSessionLocal, engine


async def run():
    """Run snapshot calculation."""
    async with AsyncSessionLocal() as session:
        print("Calculating point-in-time snapshots...")
        calculator = SnapshotCalculator(session)
        stats = await calculator.calculate_all_snapshots()
        print(f"Fights processed: {stats['fights_processed']}")
        print(f"Snapshots created: {stats['snapshots_created']}")
        if stats["errors"] > 0:
            print(f"Errors: {stats['errors']}")
        await session.commit()

    await engine.dispose()
    print("Done!")


if __name__ == "__main__":
    asyncio.run(run())
