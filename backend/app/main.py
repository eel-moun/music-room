import asyncio
from contextlib import asynccontextmanager, suppress

import structlog
from fastapi import Depends, FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.auth.router import public_router as auth_public_router
from app.auth.router import router as auth_router
from app.core import metrics
from app.core.client_headers import require_client_headers
from app.core.config import get_settings
from app.core.db import SessionDep, engine
from app.core.logging import configure_logging
from app.core.middleware import RequestLogMiddleware
from app.core.redis import RedisDep, redis_client
from app.delegation.router import router as delegation_router
from app.music.audius import audius_client
from app.music.provider import MusicProviderError, TrackNotFoundError
from app.music.router import router as music_router
from app.playlists.router import router as playlists_router
from app.realtime.rooms import rooms
from app.realtime.router import router as realtime_router
from app.users.router import router as users_router
from app.votes.router import router as votes_router

settings = get_settings()
configure_logging(settings.log_level)
log = structlog.get_logger()


@asynccontextmanager
async def lifespan(_: FastAPI):
    log.info("startup", env=settings.app_env)
    subscriber = asyncio.create_task(rooms.run_subscriber())
    yield
    subscriber.cancel()
    with suppress(asyncio.CancelledError):
        await subscriber
    await audius_client.aclose()
    await redis_client.aclose()
    await engine.dispose()


app = FastAPI(
    title="Music Room API",
    version="1.0.0",
    description=(
        "Backend of Music Room: Track Vote, Playlist Editor and Control Delegation.\n\n"
        "Every app request must send `X-Platform`, `X-Device` and `X-App-Version`. "
        "Authenticate with **Authorize** using the `access_token` from `/auth/login`. "
        "Realtime updates: WebSocket `/ws` (protocol in the `realtime` section of the README)."
    ),
    lifespan=lifespan,
)
app.add_middleware(RequestLogMiddleware)
if settings.cors_origins:
    # The mobile app doesn't need CORS (no browser); only listed web origins get it.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[o.strip() for o in settings.cors_origins.split(",")],
        allow_methods=["*"],
        allow_headers=["*"],
    )

app_headers = [Depends(require_client_headers)]
for router in (
    auth_router,
    users_router,
    music_router,
    votes_router,
    playlists_router,
    delegation_router,
):
    app.include_router(router, dependencies=app_headers)
app.include_router(auth_public_router)  # opened from email links in a browser
app.include_router(realtime_router)


# Starlette picks the most specific handler, so TrackNotFoundError wins over its parent.
@app.exception_handler(TrackNotFoundError)
async def track_not_found(_: Request, exc: TrackNotFoundError) -> JSONResponse:
    return JSONResponse(
        status_code=404,
        content={"detail": {"code": "track_not_found", "message": "Track not found"}},
    )


@app.exception_handler(MusicProviderError)
async def music_provider_error(_: Request, exc: MusicProviderError) -> JSONResponse:
    return JSONResponse(
        status_code=502,
        content={
            "detail": {"code": "provider_unavailable", "message": "Music provider unavailable"}
        },
    )


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


@app.get("/metrics", include_in_schema=False)
async def prometheus_metrics() -> Response:
    body, content_type = metrics.render()
    return Response(body, media_type=content_type)
