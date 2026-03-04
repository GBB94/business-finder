from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.database import engine, Base
from app.routers import health


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Create tables on startup (dev convenience -- use Alembic in prod)
    import app.models  # noqa: F401 — ensure all models are registered
    Base.metadata.create_all(bind=engine)
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
