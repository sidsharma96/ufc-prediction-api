# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Common Commands

```bash
# Development server
uvicorn app.main:app --reload

# Run all tests
pytest

#Always run tests before committing.

# Run single test file
pytest tests/unit/test_predictor.py -v

# Run with coverage
pytest --cov=app --cov-report=term-missing

# Lint and format
ruff check .
ruff format .

# Always run ruff checks and fix before committing.

# Type checking
mypy app

# Database migrations
alembic upgrade head              # Apply all migrations
alembic revision --autogenerate -m "description"  # Create new migration
alembic downgrade -1              # Rollback one migration

# Import data from Kaggle CSV
python scripts/import_kaggle.py /path/to/data --fights-file ufc_fights.csv

# Run backtest on historical fights
python scripts/backtest.py

# Docker development
cd docker && docker-compose up -d  # Start Postgres + Redis
```

## Architecture Overview

### Request Flow
```
FastAPI Router → Endpoint → Repository → Database
                    ↓
              PredictionEngine (for /predictions/* endpoints)
```

### Layered Architecture

**API Layer** (`app/api/v1/`)
- `endpoints/` - Route handlers (events, fighters, fights, predictions)
- `schemas/` - Pydantic request/response models
- `router.py` - Combines all endpoint routers under `/api/v1`

**Repository Layer** (`app/repositories/`)
- Generic `BaseRepository[ModelType]` with CRUD operations
- Specialized repositories: `FighterRepository`, `EventRepository`, `FightRepository`
- All use async SQLAlchemy with `AsyncSession`

**Prediction Engine** (`app/prediction_engine/`)
- `engine.py` - Main orchestrator: loads data, coordinates prediction pipeline
- `feature_extractor.py` - Extracts `FighterFeatures` from snapshots or fighter records
- `predictor.py` - `RuleBasedPredictor` calculates weighted advantages between fighters
- `weights.py` - Configurable weights for prediction factors (record, striking, grappling, etc.)
- `confidence.py` - Scores prediction confidence based on data quality

**Data Pipeline** (`app/data_pipeline/`)
- `adapters/` - Data source adapters (Kaggle CSV, ESPN API, UFC.com)
  - All implement `DataSourceAdapter` base class with `fetch_fighters()`, `fetch_events()`, `fetch_fights()`
- `import_service.py` - Orchestrates full import: fighters → events → fights
- `snapshot_calculator.py` - Creates point-in-time fighter snapshots for each fight
- `transformers.py` - Validation and normalization of raw data

### Key Domain Concepts

**Fighter Snapshots** (`FighterSnapshot` model)
- Point-in-time statistics captured before each fight
- Used for predictions and backtesting to avoid data leakage
- Created by `SnapshotCalculator` after fight data import

**Prediction Flow**
1. `PredictionEngine.predict_fight(fight_id)` loads fight + snapshots
2. `FeatureExtractor` converts snapshots to `FighterFeatures`
3. `RuleBasedPredictor.predict()` calculates advantage breakdown (record, striking, grappling, form, physical)
4. Returns `Prediction` with winner, probability, confidence, and factor breakdown

### Database Models (`app/db/models/`)
- `Fighter` - Fighter profile and career stats
- `Event` - UFC events with date, venue, completion status
- `Fight` - Individual fights linking two fighters to an event
- `FighterSnapshot` - Point-in-time stats for a fighter before a specific fight
- `Prediction` - Stored predictions for tracking accuracy
- `DataImport` - Import job tracking

### Configuration
- `app/core/config.py` - Pydantic Settings loaded from `.env`
- Automatic `postgres://` → `postgresql+asyncpg://` conversion for Fly.io
- SSL disabled for Fly.io internal Postgres connections (`app/db/session.py`)

## Deployment

Deployed to Fly.io:
- Production URL: https://ufc-prediction-api.fly.dev
- Health check: `/health`
- API docs: `/api/v1/docs`
- Release command runs `alembic upgrade head` on each deploy
