# AI usage log

The subject requires transparency on what was generated with AI. Every Claude-generated piece is listed here, along with whether I reviewed it.

| Date | What | Where | Reviewed |
|---|---|---|---|
| 2026-10-28 | Repo layout, `.gitignore`, `.env.example`, `Makefile`, this file, ADR template | repo root, `docs/` | ☐ |
| 2026-10-28 | `docker-compose.yml` (dev) + `docker-compose.prod.yml`, Makefile `prod-*` targets. Planned as mine (🧠); my first draft was reviewed, then I delegated the rewrite. | repo root | ☐ |
| 2026-10-28 | `TrackInfo` model + `MusicProvider` protocol (planned as mine 🧠, delegated) | `backend/app/music/provider.py` | ☐ |
| 2026-10-28 | `AudiusProvider` (search, stream URL, error mapping), provider exceptions, shared httpx client closed in lifespan, 5 mocked tests (planned as mine 🧠, delegated) | `backend/app/music/audius.py`, `provider.py`, `main.py`, `tests/test_audius.py` | ☐ |
| 2026-10-28 | FastAPI skeleton: settings, async DB session, Redis client, structlog JSON logging, `/health`, Alembic async setup, Dockerfile, health test | `backend/` | ☐ |
| 2026-10-28 | Music routes `GET /music/search`, `GET /music/tracks/{id}/stream`, provider dependency, 404/502 exception handlers, 9 router tests | `backend/app/music/router.py`, `main.py`, `tests/test_music_router.py` | ☐ |
