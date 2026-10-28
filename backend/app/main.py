from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.core.config import get_settings
from app.core.db import SessionDep, engine
from app.core.logging import configure_logging
from app.core.redis import RedisDep, redis_client
from app.music.audius import audius_client
from app.music.provider import MusicProviderError, TrackNotFoundError
from app.music.router import router as music_router

configure_logging(get_settings().log_level)
log = structlog.get_logger()


@asynccontextmanager
async def lifespan(_: FastAPI):
    log.info("startup", env=get_settings().app_env)
    yield
    await audius_client.aclose()
    await redis_client.aclose()
    await engine.dispose()


app = FastAPI(title="Music Room API", version="0.1.0", lifespan=lifespan)
app.include_router(music_router)


# Starlette picks the most specific handler, so TrackNotFoundError wins over its parent.
@app.exception_handler(TrackNotFoundError)
async def track_not_found(_: Request, exc: TrackNotFoundError) -> JSONResponse:
    return JSONResponse(status_code=404, content={"detail": "Track not found"})


@app.exception_handler(MusicProviderError)
async def music_provider_error(_: Request, exc: MusicProviderError) -> JSONResponse:
    return JSONResponse(status_code=502, content={"detail": "Music provider unavailable"})


@app.get("/health", tags=["system"])
async def health(session: SessionDep, redis: RedisDep) -> dict[str, str]:
    status = {"api": "ok", "postgres": "ok", "redis": "ok"}
    try:
        await session.execute(text("SELECT 1"))
    except Exception:
        log.exception("health_postgres_failed")
        status["postgres"] = "error"
    try:
        await redis.ping()
    except Exception:
        log.exception("health_redis_failed")
        status["redis"] = "error"
    return status
