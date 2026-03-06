# IdeaScope

A structured idea validation pipeline for solo bootstrappers. Score business ideas across 11 dimensions, collect evidence through three validation gates, automate community research, and make kill/continue decisions with data instead of gut feel.

## Architecture

- **Backend**: FastAPI (Python 3.12) with SQLAlchemy ORM and PostgreSQL
- **Frontend**: Next.js 15 (App Router) with React 19 and Tailwind CSS
- **Task queue**: Redis + RQ for background agent tasks
- **AI**: Claude API for evidence analysis and scoring assistance
- **Deployment**: Docker Compose (dev), single-machine friendly

## Setup

```bash
# Clone
git clone <repo-url> && cd business-finder

# Configure environment
cp .env.example .env
# Edit .env with your API keys and set COOKIE_SECURE=false for local dev

# Start all services (runs migrations automatically)
docker compose up --build

# Create your first user account
docker compose exec api python scripts/create_user.py you@example.com

# Open the app
open http://localhost:3000
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
    models/          # SQLAlchemy models
    routers/         # API route modules
    services/        # Business logic layer
    dependencies/    # FastAPI dependencies (auth)
    jobs/            # RQ background job runner
  alembic/           # Database migrations
  scripts/           # CLI utilities (create_user, backup)
  worker.py          # RQ worker entrypoint

frontend/
  src/
    app/             # Next.js App Router pages
    components/      # React components (Shell, AuthProvider)
    lib/             # API client + types
```

## Data Models

| Table | Purpose |
|-------|---------|
| users | User accounts with bcrypt password hashes |
| user_sessions | Session tokens for cookie auth |
| ideas | Business ideas with status, gates, and metadata |
| scores | 11-dimension scoring with weighted totals |
| score_history | Score snapshots over time |
| evidence | Validation evidence linked to ideas and gates |
| research_jobs | Background research task tracking |
| founder_profiles | Founder constraints and skills |
| monthly_reviews | Periodic kill/continue decisions |
| scoring_weights | Configurable dimension weights |
| metric_entries | Retention and economics metrics |
| agent_tasks | Background agent task queue |
| agent_task_steps | Ordered steps within agent tasks |
| project_secrets | Per-project encrypted key-value secrets |

## Key Rotation

When rotating API keys:
1. Update `.env` with new credentials
2. Restart affected services: `docker compose restart api worker`
3. Verify connectivity via `/health` endpoint
