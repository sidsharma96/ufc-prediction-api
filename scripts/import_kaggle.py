#!/usr/bin/env python3
"""Script to import UFC data from Kaggle CSV files.

Usage:
    python scripts/import_kaggle.py /path/to/kaggle/data

The script expects a directory containing UFC fight data in CSV format.
Common Kaggle datasets are supported, including:
- UFC Fight Data (with r_fighter, b_fighter columns)
- Similar formats with fighter1/fighter2 naming

After importing fights, the script calculates point-in-time snapshots
for all fighters, which are required for prediction.
"""

import argparse
import asyncio
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.data_pipeline.adapters import KaggleAdapter
from app.data_pipeline.import_service import ImportService
from app.data_pipeline.snapshot_calculator import SnapshotCalculator


async def run_import(
    data_dir: str,
    fights_file: str = "ufc_fights.csv",
    calculate_snapshots: bool = True,
) -> None:
    """Run the Kaggle data import.

    Args:
        data_dir: Directory containing CSV files
        fights_file: Name of the main fights CSV file
        calculate_snapshots: Whether to calculate point-in-time snapshots
    """
    # Create async engine
    engine = create_async_engine(
        str(settings.database_url),
        echo=settings.database_echo,
    )

    # Create session factory
    async_session = sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async with async_session() as session:
        # Initialize adapter
        adapter = KaggleAdapter(
            data_dir=data_dir,
            fights_file=fights_file,
        )

        # Check health
        if not await adapter.health_check():
            print(f"Error: Could not find {fights_file} in {data_dir}")
            return

        print(f"Starting import from {data_dir}/{fights_file}")
        print("-" * 50)

        # Run import
        import_service = ImportService(session)
        result = await import_service.run_import(adapter)

        # Print results
        print(f"\nImport completed: {result.status}")
        print(f"  Started: {result.started_at}")
        print(f"  Completed: {result.completed_at}")
        print()
        print("Fighters:")
        print(f"  Processed: {result.fighters_processed}")
        print(f"  Created: {result.fighters_created}")
        print(f"  Updated: {result.fighters_updated}")
        print()
        print("Events:")
        print(f"  Processed: {result.events_processed}")
        print(f"  Created: {result.events_created}")
        print(f"  Updated: {result.events_updated}")
        print()
        print("Fights:")
        print(f"  Processed: {result.fights_processed}")
        print(f"  Created: {result.fights_created}")
        print(f"  Updated: {result.fights_updated}")

        if result.errors:
            print()
            print(f"Errors ({len(result.errors)}):")
            for error in result.errors[:10]:  # Show first 10 errors
                print(f"  - {error}")
            if len(result.errors) > 10:
                print(f"  ... and {len(result.errors) - 10} more errors")

        # Calculate snapshots
        if calculate_snapshots and result.fights_created > 0:
            print()
            print("-" * 50)
            print("Calculating point-in-time snapshots...")

            calculator = SnapshotCalculator(session)
            snapshot_stats = await calculator.calculate_all_snapshots()

            print(f"  Fights processed: {snapshot_stats['fights_processed']}")
            print(f"  Snapshots created: {snapshot_stats['snapshots_created']}")
            if snapshot_stats["errors"] > 0:
                print(f"  Errors: {snapshot_stats['errors']}")

    await engine.dispose()
    print()
    print("Import complete!")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Import UFC data from Kaggle CSV files")
    parser.add_argument(
        "data_dir",
        type=str,
        help="Directory containing Kaggle CSV files",
    )
    parser.add_argument(
        "--fights-file",
        type=str,
        default="ufc_fights.csv",
        help="Name of the fights CSV file (default: ufc_fights.csv)",
    )
    parser.add_argument(
        "--no-snapshots",
        action="store_true",
        help="Skip calculating point-in-time snapshots",
    )

    args = parser.parse_args()

    # Validate data directory
    data_path = Path(args.data_dir)
    if not data_path.exists():
        print(f"Error: Directory not found: {args.data_dir}")
        sys.exit(1)

    if not data_path.is_dir():
        print(f"Error: Not a directory: {args.data_dir}")
        sys.exit(1)

    # Run import
    asyncio.run(
        run_import(
            data_dir=args.data_dir,
            fights_file=args.fights_file,
            calculate_snapshots=not args.no_snapshots,
        )
    )


if __name__ == "__main__":
    main()
