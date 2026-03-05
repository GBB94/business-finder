from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database import engine, Base, SessionLocal
from app.routers import health
from app.routers import ideas, scoring_weights, scores, evidence, monthly_reviews, founder_profile, metrics


def _seed_scoring_weights(db):
    """Insert default scoring weights for the default user if none exist."""
    from app.models.config import ScoringWeight, DEFAULT_WEIGHTS

    existing = db.query(ScoringWeight).filter_by(user_id=settings.DEFAULT_USER_ID).first()
    if existing:
        return
    for dimension, weight in DEFAULT_WEIGHTS.items():
        db.add(ScoringWeight(
            user_id=settings.DEFAULT_USER_ID,
            dimension=dimension,
            weight=weight,
        ))
    db.commit()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Create tables on startup (dev convenience -- use Alembic in prod)
    import app.models  # noqa: F401 — ensure all models are registered
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    try:
        _seed_scoring_weights(db)
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
app.include_router(ideas.router)
app.include_router(scoring_weights.router)
app.include_router(scores.router)
app.include_router(evidence.router)
app.include_router(monthly_reviews.router)
app.include_router(founder_profile.router)
app.include_router(metrics.router)
