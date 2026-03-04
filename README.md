# IdeaScope

A structured idea validation pipeline for solo bootstrappers. Score business ideas across 11 dimensions, collect evidence through three validation gates, automate community research, and make kill/continue decisions with data instead of gut feel.

## Architecture

- **Backend**: FastAPI (Python 3.12) with SQLAlchemy ORM and SQLite
- **Frontend**: Next.js 15 (App Router) with React 19 and Tailwind CSS
- **Task queue**: Redis + RQ for background research jobs
- **AI**: Claude API for evidence analysis and scoring assistance
- **Deployment**: Docker Compose (dev), single-machine friendly

## Setup

```bash
# Clone
git clone <repo-url> && cd business-finder

# Configure environment
cp .env.example .env
# Edit .env with your API keys

# Start all services
docker-compose up --build
```

- API: http://localhost:8000
- Frontend: http://localhost:3000
- API docs: http://localhost:8000/docs

## Project Structure

```
backend/
  app/
    main.py          # FastAPI app + lifespan
    config.py        # Pydantic Settings
    database.py      # SQLAlchemy engine + session
    models/          # SQLAlchemy models (7 tables)
    routers/         # API route modules
    services/        # Business logic layer
    integrations/    # External API adapters (Reddit, HN, Claude)
    jobs/            # RQ background job definitions
  alembic/           # Database migrations
  worker.py          # RQ worker entrypoint

frontend/
  src/
    app/             # Next.js App Router pages
    components/      # React components
    hooks/           # Custom React hooks
    lib/             # API client + utilities
```

## Data Models

| Table | Purpose |
|-------|---------|
| ideas | Business ideas with status, gates, and metadata |
| scores | 11-dimension scoring with weighted totals |
| evidence | Validation evidence linked to ideas and gates |
| research_jobs | Background research task tracking |
| founder_profiles | Founder constraints and skills |
| monthly_reviews | Periodic kill/continue decisions |
| scoring_weights | Configurable dimension weights |

## Key Rotation

When rotating API keys:
1. Update `.env` with new credentials
2. Restart affected services: `docker-compose restart api worker`
3. Verify connectivity via `/health` endpoint
