# CLAUDE.md

Music Room: a collaborative music mobile app built from the subject in `musicroom.pdf` (v6). Solo project, 10-day schedule in `PLAN.md` (7 build days + 3 review days, started 2026-10-27). Check `PLAN.md` for the current day's tasks before starting work.

## Working agreement (from the subject's AI rules — non-negotiable)

- The user owns every design decision and must be able to explain every line in the defense. Propose options with trade-offs; don't decide silently.
- Task ownership is marked in `PLAN.md`:
  - 🧠 **User writes** (concurrency, security, token logic, policies, realtime, Redis, load testing, ADRs). Explain the concept briefly with a small example, then let the user write it. Review it; don't rewrite it unasked.
  - 🤖 **Claude generates** (scaffolding, boilerplate, CRUD, screens, configs, test suites). The user reviews.
- Log every Claude-generated piece in `docs/AI_USAGE.md` (what, where, reviewed by user y/n).
- The user is an experienced dev from AI/ML/MLOps; knows Postgres, FastAPI, Docker, GitHub Actions, React. New to Redis, Grafana, load testing, React Native. Be concise; relate to MLOps where useful.
- Accuracy over speed: say when something is unverified, check library docs/versions rather than guessing.

## Scope

- **All 3 services:** Track Vote, Playlist Editor, Control Delegation.
- Auth: email/password (email verification + password reset) and **Google only** (subject: Facebook *or* Google), plus account linking.
- Profiles: public / friends-only / private fields + music preferences.
- Mandatory part only. No bonuses (they're only graded if the mandatory part is perfect).

## Stack

- **Backend:** FastAPI (REST + JSON, Swagger auto-docs), Python with uv, SQLAlchemy 2 async + asyncpg, Alembic, pydantic-settings, ruff, pytest.
- **Data:** PostgreSQL (relational + JSONB) is the single source of truth. Redis for rate limiting, refresh-token support, and pub/sub between workers.
- **Realtime:** FastAPI WebSocket; events fanned out across workers via Redis pub/sub.
- **Mobile:** React Native with Expo (development build, needed for Google Sign-In), expo-router, expo-secure-store for tokens, typed API client generated from FastAPI's OpenAPI.
  - **Cross-platform code (Android + iOS)**: no Android-only or iOS-only APIs without a `Platform` fallback; use safe areas; per-platform config (Google OAuth client IDs, iOS background audio, location permission strings) lives in the Expo app config.
  - **Days 1–2: no phone work.** Verify everything on the PC (Swagger, browser, CLI/Python clients). Phone testing starts on Day 3.
  - **Validation happens on a physical Android phone** (dev build via `npx expo run:android`; the dev machine is Linux). Occasional checks on a **physical iPhone via Expo Go** (no Mac / no paid Apple account).
  - **Keep the app Expo Go-compatible**: Google Sign-In's native module isn't in Expo Go, so load it only when available and hide the Google button otherwise (iOS checks use email login). Don't add other native modules that Expo Go lacks without discussing it.
  - Phones reach the backend via the PC's LAN IP (`http://192.168.x.x:8000`), set in the app's backend-URL settings.
- **Music:** Audius (primary) / Jamendo (fallback) behind a `MusicProvider` adapter. Store only track references (provider, external_id, title, artist, duration, artwork), never audio.
- **Observability:** structlog JSON logs → Grafana Alloy → Loki → Grafana; Prometheus metrics. Promtail is EOL — don't use it.
- **Infra/CI:** Docker Compose, Makefile, mailpit for dev emails, GitHub Actions, k6 for load tests.
- Rejected (don't reopen): GraphQL, pg_graphql, graph databases, Firebase, Spotify (5-user dev-mode cap), Deezer (new apps closed).

## Architecture rules

- The mobile app is a thin "remote control": it sends commands via REST, receives state via WebSocket, and never trusts its own state over the server's.
- The backend URL must be configurable in the app (settings screen).
- **All authorization goes through `app/policies/`** (visibility, invitations, licenses). No ad-hoc permission checks in routes.
- **Realtime goes through the shared `app/realtime/` rooms module.** Event envelope: `{type, room, seq, payload}`. On reconnect the client refetches.
- Concurrency:
  - Votes: `UNIQUE(event_id, track_id, user_id)`, ranking computed server-side (votes DESC, suggested_at ASC), now-playing track excluded from voting.
  - Playlists: fractional positions + playlist `version`; writes carry the expected version, return **409** on mismatch.
  - Time-window licenses are checked with server time. Client GPS is spoofable — a documented hazard.
- Every request carries `X-Platform`, `X-Device`, `X-App-Version`; middleware logs every action with them.
- Auth: argon2 (run in a threadpool), short-lived access JWT + rotating refresh tokens with reuse detection, Redis rate limits on auth endpoints. Google ID tokens are verified server-side.

## Repo layout

```
backend/app/{core,auth,users,policies,realtime,music,votes,playlists,delegation}
backend/migrations/   backend/tests/
mobile/               Expo app
infra/                Grafana/Loki/Alloy/Prometheus config
loadtest/             k6 scripts
docs/                 adr/, SECURITY.md, LOAD_TEST.md, AI_USAGE.md
```

## Hard rules

- **No secrets in git, ever.** Credentials live in `.env` (gitignored); commit `.env.example` only. Leaked credentials fail the project.
- Don't commit third-party libraries; dependencies must install from a clean clone via `make` / Docker.
- Every significant decision gets a short ADR in `docs/adr/` (written by the user).
- Every layer gets tests; concurrency paths get explicit parallel tests.

## Commands

Run `make help` for the full list. Main targets (run from the repo root; most exec into the `api` container):
- `make up` / `make down` / `make logs` / `make ps`: start, stop, follow API logs, list services
- `make migrate` / `make revision m="msg"`: apply / autogenerate Alembic migrations
- `make test` / `make lint` / `make format`: pytest, ruff check + format check, auto-format
- `make psql` / `make redis-cli` / `make shell`: open a client inside the containers
- `make prod-up` / `make prod-down` / `make prod-logs`: production-like stack from `docker-compose.prod.yml` (needs a gitignored `.env.prod`)
- `make mobile-install` / `make mobile`: install mobile deps, start Expo

Compose notes: dev runs 1 worker with `--reload` (code mounted); prod runs the Dockerfile CMD with 2 workers, no published DB/Redis ports, memory limits only (this host's kernel rejects `cpus` limits). Dev Redis is published on host port **6380** because a host `redis-server` already uses 6379.

Backend without Docker (from `backend/`): `uv run pytest`, `uv run ruff check .`. The API container runs `uvicorn ... --workers 2` on purpose (cross-worker realtime must be tested).
