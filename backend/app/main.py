from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from passlib.hash import bcrypt

from app.config import settings
from app.database import SessionLocal
from app.routers import health
from app.routers import (
    auth,
    ideas,
    scoring_weights,
    scores,
    evidence,
    monthly_reviews,
    founder_profile,
    metrics,
    research,
    agent_tasks,
    project_secrets,
)


def _seed_default_user(db):
    """Create a default user if none exist."""
    from app.models.user import User

    if db.query(User).first():
        return
    user = User(
        email=settings.DEFAULT_USER_EMAIL,
        display_name="Admin",
        password_hash=bcrypt.hash(settings.DEFAULT_USER_PASSWORD),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _seed_scoring_weights(db):
    """Insert default scoring weights for the first user if none exist."""
    from app.models.config import ScoringWeight, DEFAULT_WEIGHTS
    from app.models.user import User

    user = db.query(User).first()
    if not user:
        return
    existing = db.query(ScoringWeight).filter_by(user_id=user.id).first()
    if existing:
        return
    for dimension, weight in DEFAULT_WEIGHTS.items():
        db.add(ScoringWeight(
            user_id=user.id,
            dimension=dimension,
            weight=weight,
        ))
    db.commit()


@asynccontextmanager
async def lifespan(app: FastAPI):
    db = SessionLocal()
    try:
        _seed_default_user(db)
        _seed_scoring_weights(db)
    except Exception:
        # Tables may not exist yet if migrations haven't run.
        # docker-compose runs alembic upgrade head before uvicorn,
        # but guard against manual / dev-server starts without migrations.
        import logging
        logging.getLogger(__name__).warning(
            "Seed failed — have you run 'alembic upgrade head'?"
        )
    finally:
        db.close()

    yield


app = FastAPI(
    title="IdeaScope API",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(auth.router)
app.include_router(ideas.router)
app.include_router(scoring_weights.router)
app.include_router(scores.router)
app.include_router(evidence.router)
app.include_router(monthly_reviews.router)
app.include_router(founder_profile.router)
app.include_router(metrics.router)
app.include_router(research.router)
app.include_router(agent_tasks.router)
app.include_router(project_secrets.router)
