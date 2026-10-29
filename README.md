# Music Room

A collaborative music app: a mobile client (React Native / Expo) for a FastAPI backend that is the single source of truth. The 3 services of the subject are implemented:

- **Track Vote**: guests suggest tracks and vote; the most voted track plays next. Public or private events; voting open to everyone, to invited users only, or to people at the venue during a time window.
- **Playlist Editor**: several people edit one playlist in real time, with conflict detection when two of them change it at once. Public or private; editable by everyone or by invited users only.
- **Control Delegation**: each phone is a device; its owner gives friends control of its playback (playback and/or volume, optionally until a time), device by device.

Plus accounts (email + password with email verification and password reset, or Google, and linking Google to an existing account), profiles with public / friends-only / private information and music preferences, and friends.

## Architecture

```
 Phone (Expo app)                          Server (Docker Compose)
 ┌──────────────────┐   REST + JSON    ┌──────────────────────────────┐
 │ screens          │ ───────────────▶ │ FastAPI (uvicorn, N workers) │──▶ PostgreSQL  (all data)
 │ "remote control" │                  │  policies/ (authorization)   │──▶ Redis  (rate limits,
 │                  │ ◀─────────────── │  realtime/ (rooms)           │◀──    pub/sub, device state)
 └──────────────────┘   WebSocket      └──────────────────────────────┘──▶ Audius API (music)
                        (push only)            │ JSON logs, /metrics
                                               ▼
                                Alloy → Loki ─┐
                                Prometheus ───┴─▶ Grafana
```

- The app only sends commands (REST) and receives state (WebSocket). It never trusts its own state over the server's: after a reconnect, or when it spots a gap in event sequence numbers, it refetches.
- Each uvicorn worker keeps its own sockets; events go through **Redis pub/sub**, so a vote handled by one worker reaches phones connected to any worker.
- Concurrency is handled by the database: unique constraints for votes, optimistic locking (`version` + 409) for playlists, a row lock for "next track".
- All authorization rules are pure functions in `backend/app/policies/`, shared by REST and WebSocket.

Decisions and their reasons are in [`docs/adr/`](docs/adr/).

## Quick start

Requirements: Docker with Compose, `make`, and [uv](https://docs.astral.sh/uv/) only to run the scripts outside Docker.

```bash
cp .env.example .env        # then edit the secrets (make up creates it if missing)
make up                     # api, postgres, redis, mailpit, with hot reload
make migrate                # create the tables
open http://localhost:8000/docs     # Swagger: every endpoint, inputs and outputs
open http://localhost:8025          # mailpit: the emails the API sends
```

Then register in Swagger (`POST /auth/register`), open the verification link from mailpit, log in, and click **Authorize** with the `access_token`. App endpoints require the headers `X-Platform`, `X-Device` and `X-App-Version` (Swagger shows the fields).

### Production-like stack

```bash
cp .env.example .env.prod   # real secrets: JWT_SECRET=$(openssl rand -hex 32), real SMTP
make prod-up                # 2 workers, non-root image, migrations at startup, no DB/Redis ports
make obs-up                 # + Loki, Alloy, Prometheus, Grafana on http://localhost:3000
```

## Mobile app

```bash
cd mobile && cp .env.example .env    # EXPO_PUBLIC_API_URL=http://<PC LAN IP>:8000
make mobile-install                  # needs Node 24 LTS
make mobile                          # Expo dev server
```

- **Android (full app, including Google sign-in)**: development build, `npx expo run:android` with the phone connected over USB.
- **iPhone (Expo Go)**: scan the QR code. Everything works except Google sign-in, which needs native code that Expo Go doesn't have; the button is hidden there.
- The backend address can be changed in the app (**Server settings** on the login screen), with a connection test. The phone and the PC must be on the same network.
- `make mobile-check` typechecks and lints the app in Docker (no local Node needed). `make mobile-api` regenerates the app's TypeScript API types from the backend's OpenAPI.

## Realtime protocol (`/ws`)

| Direction | Message |
|---|---|
| → | `{"type": "auth", "token": "<access token>"}` first, within 10 s |
| ← | `{"type": "ready", "payload": {"user_id", "worker"}}` |
| → | `{"type": "subscribe", "room": "event:<id>"}` (also `playlist:<id>`, `device:<id>`, `user:<id>`) |
| ← | `{"type": "subscribed", "room", "payload": {"seq"}}` or `{"type": "error", ...}` |
| ← | `{"type": "queue.updated", "room", "seq", "payload"}` and other events, `seq` +1 per room |
| ← | `{"type": "unsubscribed", "room", "payload": {"reason": "access_revoked"}}` |
| → | `{"type": "unsubscribe", "room"}`, `{"type": "ping"}` |

Subscribing applies the same rules as reading the resource over REST. Events: `queue.updated`, `event.updated`, `event.deleted`, `playlist.updated` (with the new version), `playlist.deleted`, `device.command`, `device.state`, `device.deleted`, `friend.request`, `friend.accepted`, `event.invited`, `playlist.invited`, `delegation.granted`, `delegation.revoked`.

## Tests and quality

```bash
make test        # 152 backend tests (separate test database, wiped before each test)
make lint        # ruff
make check-realtime   # end-to-end: 2 sockets on 2 different workers get the same event (prod stack)
```

What the tests cover:
- unit tests of every policy;
- auth: token rotation, reuse detection, rate limits, Google, email flows;
- concurrency (50 simultaneous votes, conflicting playlist moves, parallel suggestions, double "next");
- an IDOR sweep where user B attacks user A's resources;
- the realtime layer, with two room managers on one Redis.

CI (GitHub Actions) runs lint, migrations (`alembic upgrade` + `alembic check`) and the tests on every push, and typechecks and lints the mobile app.

## Documentation

| | |
|---|---|
| [`docs/adr/`](docs/adr/) | Architecture decisions: stack, music provider, REST + WebSocket, rate limiting, vote concurrency, location license, playlist concurrency, control delegation |
| [`docs/SECURITY.md`](docs/SECURITY.md) | Protections in place (with the tests that prove them) and the remaining hazards |
| [`docs/LOAD_TEST.md`](docs/LOAD_TEST.md) | Server specs, k6 scenarios, results: about **800 simultaneous users** on the default configuration, and what limits it |
| [`docs/AI_USAGE.md`](docs/AI_USAGE.md) | What was generated with AI, and what was reviewed |

## Layout

```
backend/app/
  core/        config, database, Redis, security, logging + metrics middleware, rate limits
  auth/        register, login, refresh rotation, email flows, Google
  users/       profiles, friends
  policies/    every authorization rule (pure functions)
  realtime/    rooms over Redis pub/sub, WebSocket endpoint
  music/       MusicProvider protocol, Audius adapter
  votes/       Track Vote
  playlists/   Playlist Editor
  delegation/  Control Delegation
backend/migrations/   Alembic
backend/tests/        pytest
backend/scripts/      seed users, realtime end-to-end check
mobile/               Expo app (src/app = screens, src/api = typed client)
infra/                Alloy, Prometheus, Grafana provisioning + dashboard
loadtest/             k6 scenarios
```
