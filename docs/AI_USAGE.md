# AI usage log

The subject requires transparency on what was generated with AI. Every Claude-generated piece is listed here, along with whether I reviewed it.

**How the project was built:** I chose the stack and the architecture. The plan split the work between parts I'd write (🧠: concurrency, security, tokens, policies, realtime, load testing, ADRs) and parts Claude would generate (🤖). On 2026-10-29 I delegated the rest of the build to Claude to finish in time. The plan from then on: review every piece with Claude (explanations, line by line), then rewrite the critical parts myself. The "Reviewed" column tracks that.

| Date | What | Where | Reviewed |
|---|---|---|---|
| 2026-10-28 | Repo layout, `.gitignore`, `.env.example`, `Makefile`, this file, ADR template | repo root, `docs/` | ☐ |
| 2026-10-28 | `docker-compose.yml` (dev) + `docker-compose.prod.yml`, Makefile `prod-*` targets. Planned as mine (🧠); my first draft was reviewed, then I delegated the rewrite. | repo root | ☐ |
| 2026-10-28 | `TrackInfo` model + `MusicProvider` protocol (planned as mine 🧠, delegated) | `backend/app/music/provider.py` | ☐ |
| 2026-10-28 | `AudiusProvider` (search, stream URL, error mapping), provider exceptions, shared httpx client closed in lifespan, 5 mocked tests (planned as mine 🧠, delegated) | `backend/app/music/audius.py`, `provider.py`, `main.py`, `tests/test_audius.py` | ☐ |
| 2026-10-28 | FastAPI skeleton: settings, async DB session, Redis client, structlog JSON logging, `/health`, Alembic async setup, Dockerfile, health test | `backend/` | ☐ |
| 2026-10-28 | Music routes `GET /music/search`, `GET /music/tracks/{id}/stream`, provider dependency, 404/502 exception handlers, router tests | `backend/app/music/router.py`, `main.py`, `tests/test_music_router.py` | ☐ |
| 2026-10-28 | GitHub Actions CI: ruff check + format check + pytest, Postgres/Redis service containers | `.github/workflows/ci.yml` | ☐ |
| 2026-10-29 | Realtime spike (planned as mine 🧠, delegated): `RoomManager`, Redis pub/sub fan-out, per-room seq, reconnect loop, lifespan task, Redis tests | `backend/app/realtime/`, `tests/test_rooms.py` | ☐ |
| 2026-10-29 | ADR-001/002/003 drafts (mine 🧠, to rewrite) | `docs/adr/` | ☐ |
| 2026-10-29 | **Data model** (14 tables) + initial migration, including the hand-fixed circular FK found by `alembic check` (🧠 planned, delegated) | `backend/app/*/models.py`, `migrations/versions/` | ☐ |
| 2026-10-29 | **Auth** (🧠 token logic, delegated): argon2, JWT access tokens, refresh rotation with reuse detection, email verification and reset, change password, Google login and linking, Redis rate limits | `backend/app/auth/`, `app/core/security.py`, `app/core/ratelimit.py`, `app/core/email.py` | ☐ |
| 2026-10-29 | Request log + metrics middleware, required device headers, payload limit (🧠 planned, delegated) | `backend/app/core/middleware.py`, `client_headers.py`, `metrics.py` | ☐ |
| 2026-10-29 | Profiles (visibility blocks) and friends | `backend/app/users/` | ☐ |
| 2026-10-29 | **Policies module** (🧠, delegated): visibility, vote licenses incl. location + time, playlist licenses, device control, haversine | `backend/app/policies/` | ☐ |
| 2026-10-29 | **Track Vote** (🧠 vote/ranking/locking, delegated): events, invites, suggestions, idempotent votes, ranking query, `next` with row lock | `backend/app/votes/` | ☐ |
| 2026-10-29 | **Playlist Editor** (🧠, delegated): optimistic locking, fractional positions + rebalance, members | `backend/app/playlists/` | ☐ |
| 2026-10-29 | **Control Delegation** (🧠, delegated): devices, delegations, commands, state in Redis | `backend/app/delegation/` | ☐ |
| 2026-10-29 | **Realtime v2** (🧠, delegated): authenticated `/ws` protocol, room access via policies, cross-worker kick, send timeout | `backend/app/realtime/` | ☐ |
| 2026-10-29 | Test suite (152 tests): conftest with test DB and fakes, auth, users, policies, votes and playlist **concurrency tests**, delegation, IDOR sweep, logging/metrics | `backend/tests/` | ☐ |
| 2026-10-29 | Prod hardening: start script (migrations, multiprocess metrics), non-root image, configurable workers and DB pool | `backend/start.sh`, `Dockerfile`, compose files | ☐ |
| 2026-10-29 | Scripts: seed users / tokens, end-to-end realtime check across workers | `backend/scripts/` | ☐ |
| 2026-10-29 | **Observability** (🤖 configs; 🧠 dashboard + LogQL queries, delegated): compose file, Alloy, Prometheus, Grafana provisioning, dashboard | `docker-compose.observability.yml`, `infra/` | ☐ |
| 2026-10-29 | **Load testing** (🧠, delegated): k6 scenarios, runs, and the report with measured results | `loadtest/`, `docs/LOAD_TEST.md` | ☐ |
| 2026-10-29 | `docs/SECURITY.md` (🧠, delegated), ADR-004 to 008 drafts (🧠, to rewrite) | `docs/` | ☐ |
| 2026-10-29 | **Mobile app**: Expo project, API client with refresh, realtime client, device agent, host player, all screens, app config | `mobile/` | ☐ |
| 2026-10-29 | README files, CI jobs for migrations and the mobile app | `README.md`, `mobile/README.md`, `.github/workflows/ci.yml` | ☐ |
