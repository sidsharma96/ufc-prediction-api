# UFC Prediction API

A production-ready REST API for UFC fight predictions, events, and leaderboards.

## Features

- **Events & Fighters**: Comprehensive UFC event and fighter data
- **Fight Predictions**: Rule-based prediction engine with confidence scoring
- **User Accounts**: JWT authentication with prediction tracking
- **Leaderboards**: Rankings by various time periods
- **Betting Odds**: Integration with The Odds API

## Quick Start

### Prerequisites

- Python 3.11+
- Docker & Docker Compose
- PostgreSQL 16+ (via Docker)
- Redis 7+ (via Docker)

### Setup

1. **Clone and install dependencies:**
   ```bash
   cd ufc-prediction-api
   python -m venv venv
   source venv/bin/activate  # or `venv\Scripts\activate` on Windows
   pip install -e ".[dev]"
   ```

2. **Start infrastructure:**
   ```bash
   cd docker
   docker-compose up -d
   ```

3. **Configure environment:**
   ```bash
   cp .env.example .env
   # Edit .env with your settings
   ```

4. **Run database migrations:**
   ```bash
   alembic upgrade head
   ```

5. **Start the server:**
   ```bash
   uvicorn app.main:app --reload
   ```

6. **Access the API:**
   - API: http://localhost:8000
   - Docs: http://localhost:8000/docs
   - pgAdmin: http://localhost:5050 (admin@admin.com / admin)

## Project Structure

```
ufc-prediction-api/
├── alembic/                  # Database migrations
├── app/
│   ├── api/v1/              # API endpoints
│   │   ├── endpoints/       # Route handlers
│   │   └── schemas/         # Request/response models
│   ├── core/                # Config, security, middleware
│   ├── db/models/           # SQLAlchemy ORM models
│   ├── repositories/        # Data access layer
│   ├── services/            # Business logic
│   ├── prediction_engine/   # Prediction algorithms
│   └── data_pipeline/       # Data import adapters
├── tests/
├── scripts/                 # Utility scripts
└── docker/                  # Docker configuration
```

## API Endpoints

| Endpoint | Description |
|----------|-------------|
| `POST /v1/auth/register` | Create account |
| `POST /v1/auth/login` | Get JWT tokens |
| `GET /v1/events` | List events |
| `GET /v1/fighters` | List fighters |
| `GET /v1/fights/{id}/prediction` | Get fight prediction |
| `GET /v1/leaderboards` | View rankings |

See full documentation at `/docs` when running.

## Development

```bash
# Run tests
pytest

# Run with coverage
pytest --cov=app

# Lint
ruff check .

# Type check
mypy app
```

## License

MIT
