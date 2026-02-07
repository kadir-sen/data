from contextlib import asynccontextmanager
from collections.abc import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.cache import close_redis
from app.config import settings
from app.db import engine
from app.logging_config import configure_logging
from app.middleware.observability import ObservabilityMiddleware
from app.middleware.rate_limit import RateLimitMiddleware
from app.routers import (
    audit, auth, connectors, effort, health, metrics,
    observability, reports, sprints, work_items,
)

configure_logging()


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncGenerator[None, None]:
    # Startup: engine is already created; nothing extra needed.
    yield
    # Shutdown: dispose the connection pool and Redis cleanly.
    await engine.dispose()
    await close_redis()


app = FastAPI(
    title="Case API",
    version="0.1.0",
    description=(
        "Dashboard API for sprint management, work-item tracking, effort logging, "
        "and metrics reporting. Provides chart-ready series and table-ready rows."
    ),
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan,
)

# Middleware (order matters — outermost first)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.api_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(RateLimitMiddleware, limit=60, window=60)
app.add_middleware(ObservabilityMiddleware)

# Routers
app.include_router(health.router)
app.include_router(auth.router)
app.include_router(connectors.router)
app.include_router(audit.router)
app.include_router(sprints.router)
app.include_router(work_items.router)
app.include_router(effort.router)
app.include_router(reports.router)
app.include_router(metrics.router)
app.include_router(observability.router)


@app.get("/", tags=["root"])
async def root() -> dict[str, str]:
    return {"message": "Case API is running"}
