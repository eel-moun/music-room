# Music Room — 10-Day Plan

**Format:** 7 build days × 6h, then 3 review days.
**Scope:** all 3 services (Track Vote, Playlist Editor, Control Delegation), Google login only, mandatory part only.
**Stack:** FastAPI (REST) · PostgreSQL · Redis · Docker Compose · React Native (Expo) · Loki + Alloy + Grafana + Prometheus · k6 · GitHub Actions.
**Music:** Audius (primary) behind a `MusicProvider` adapter, Jamendo as fallback.

**Who does what**
- **You:** architecture, data model, every concurrency/security-critical path, every ADR. You must be able to explain every line.
- **Claude:** scaffolding, boilerplate, repetitive CRUD/screens, test suites, configs. You review all of it, and it is logged in `docs/AI_USAGE.md`.
- **Legend:** 🧠 = you write (learning/critical) · 🤖 = Claude generates, you review · 🔍 = review together

**Overflow rule:** anything unfinished on day N moves to the review days, never into day N+1's critical path. If a day runs over, cut in this order: Prometheus → Grafana dashboards polish → UI polish. **Never** cut security, logging of actions, load testing, or any service.

---

## Repo layout (target)

```
music-room/
├── backend/            FastAPI app (uv, ruff, pytest)
│   ├── app/
│   │   ├── core/       config, db, security, logging, redis
│   │   ├── auth/       email/password, Google, tokens
│   │   ├── users/      profiles, friends
│   │   ├── policies/   visibility + license checks (shared)
│   │   ├── realtime/   WebSocket rooms + Redis pub/sub (shared)
│   │   ├── music/      MusicProvider adapter (Audius, Jamendo)
│   │   ├── votes/      Track Vote service
│   │   ├── playlists/  Playlist Editor service
│   │   └── delegation/ Control Delegation service
│   ├── migrations/     Alembic
│   └── tests/
├── mobile/             Expo app (expo-router)
├── infra/              compose files, Grafana/Loki/Alloy/Prometheus config
├── loadtest/           k6 scripts
├── docs/               adr/, SECURITY.md, LOAD_TEST.md, AI_USAGE.md
├── .github/workflows/
├── docker-compose.yml
├── Makefile
└── .env.example        (.env is gitignored)
```

---

## Day 1 — Foundations & risk spikes

**Goal:** every risky unknown proven working before writing features.

| Time | Task | Who |
|---|---|---|
| 0:00–0:45 | Repo layout, `.gitignore`, `.env.example`, `Makefile` (`up`, `down`, `test`, `migrate`, `lint`, `logs`) | 🤖 |
| 0:45–1:30 | `docker-compose.yml`: api, postgres, redis, mailpit, with healthchecks and volumes | 🧠 |
| 1:30–2:15 | FastAPI skeleton: pydantic-settings config, async SQLAlchemy 2 + asyncpg, Alembic, `/health`, structlog JSON logs | 🤖 |
| 2:15–3:45 | **Spike: music.** Audius key → `MusicProvider` protocol + `AudiusProvider.search()` / `get_stream_url()` + `/music/*` routes → verified on the PC (Swagger + the stream URL plays in a browser). **Exit rule: 2h max, otherwise switch to Jamendo.** | 🧠 |
| 3:45–5:15 | **Spike: realtime.** FastAPI WebSocket + Redis pub/sub, run with **2 uvicorn workers** (`make prod-up`), prove a message from worker A reaches a client on worker B, using 2 command-line/Python clients on the PC | 🧠 (Redis learning) |
| 5:15–6:00 | GitHub Actions: ruff + pytest (with Postgres/Redis service containers). ADR-001 (stack), ADR-002 (music provider), ADR-003 (REST + WS) | 🤖 CI · 🧠 ADRs |

**Done when:** `make up` starts everything from a clean clone · a track plays in the PC browser from our API · a cross-worker WS message works · CI is green.
**You learn:** Redis basics (data types, pub/sub).
**Deferred to Day 3:** everything phone-related (LAN access, Expo shell, playback on device). Install Node LTS, Android platform-tools and Expo Go before Day 3.

---

## Day 2 — Authentication & action logging

| Time | Task | Who |
|---|---|---|
| 0:00–1:00 | Data model: `users`, `auth_identities` (provider, subject), `refresh_tokens` (family, hash, revoked), `email_tokens` (purpose, hash, expires). Migration. | 🧠 |
| 1:00–2:30 | Email/password: register, argon2 hashing (in threadpool), verification email via mailpit, login, **refresh rotation with reuse detection** (revoke the whole family), logout, forgot/reset | 🧠 token logic · 🤖 endpoints & email templates |
| 2:30–3:30 | **Rate limiting in Redis** (login, register, forgot-password, per IP + per account). Choose fixed vs sliding window → ADR-004 | 🧠 |
| 3:30–4:30 | Google sign-in: server-side ID token verification, find-or-create user, **link Google to existing account** endpoint | 🧠 |
| 4:30–5:15 | Request-context middleware: require `X-Platform`, `X-Device`, `X-App-Version`; log every action (user, route, status, latency, device info) | 🧠 |
| 5:15–6:00 | pytest suite for auth (happy paths, expired tokens, reused refresh token, rate limit hit) | 🤖 |

**Done when:** the full auth flow works via Swagger · tests are green · every request produces a structured log line with device info.
**You learn:** token rotation, Redis counters/TTL, OAuth ID token verification.

---

## Day 3 — Profiles, friends & mobile foundation

| Time | Task | Who |
|---|---|---|
| 0:00–1:15 | Profiles: public / friends-only / private fields + music preferences (JSONB). Friendship requests (send, accept, decline, remove). Response filtering by viewer relationship. | 🧠 visibility logic · 🤖 CRUD |
| 1:15–1:45 | Generate a typed TS client from FastAPI's OpenAPI (`openapi-typescript`) — the contract between backend and app | 🤖 |
| — | **First phone session (deferred from Day 1):** phone reaches `http://<LAN-IP>:8000/health`; Expo shell runs on the Android phone (dev build) and the iPhone (Expo Go); a track from `/music/*` plays on both. Absorbs ~1h, taken from the screens block below. | 🤖 shell · 🧠 device setup |
| 1:45–3:00 | Mobile core: expo-router structure, API client, auth store with **expo-secure-store**, automatic token refresh, **configurable backend URL** settings screen, device-info headers | 🧠 refresh logic · 🤖 rest |
| 3:00–4:00 | Google Sign-In on mobile (needs an Expo **development build**) | 🧠 |
| 4:00–6:00 | Screens: login, register, forgot password, profile (view/edit), friends, settings | 🤖 |

**Done when:** you can register, verify email, log in (email or Google), edit your profile, and add a friend — all from the phone.
**You learn:** React Native differences from React (View/Text, StyleSheet, navigation, secure storage, dev builds).

---

## Day 4 — Shared foundations + Track Vote backend

| Time | Task | Who |
|---|---|---|
| 0:00–1:30 | **Policy module** (shared by all 3 services): visibility (public/private + invitations), licenses (everyone / invited only / location + time window). Pure functions, fully unit-tested. | 🧠 |
| 1:30–2:30 | **Generic realtime rooms**: authenticated `/ws`, subscribe/unsubscribe to a room, Redis pub/sub fan-out, event envelope `{type, room, seq, payload}`, reconnect → client refetches | 🧠 |
| 2:30–4:30 | Track Vote: `events`, `event_invites`, `event_tracks`, `votes` with `UNIQUE(event_id, track_id, user_id)`. Suggest, vote, unvote, ranking (votes DESC, suggested_at ASC), now-playing locked out of voting, server-side time check, location check (haversine) | 🧠 vote/ranking/locking · 🤖 CRUD |
| 4:30–5:15 | **Concurrency test**: 50 parallel votes, same and different tracks → exact counts, no duplicates | 🧠 |
| 5:15–6:00 | Endpoint tests + ADR-005 (vote concurrency), ADR-006 (spoofable GPS = known hazard) | 🤖 tests · 🧠 ADRs |

**Done when:** a vote from one client updates every connected client's queue in realtime, across 2 workers, and the concurrency test passes.

---

## Day 5 — Track Vote mobile + Playlist Editor backend

| Time | Task | Who |
|---|---|---|
| 0:00–2:30 | Track Vote mobile: event list/search, create event (visibility, license, location/time), event screen with live queue, vote, search + suggest tracks, host player (plays the top track, advances the queue) | 🤖 screens · 🧠 WS hook + player logic |
| 2:30–4:30 | Playlist Editor backend: `playlists`, `playlist_members`, `playlist_tracks` with **fractional positions** + playlist `version`. Add/move/remove with expected version → **409 on conflict**. Reuses policies + rooms. | 🧠 |
| 4:30–5:30 | Concurrency tests: 2 users moving the same / different tracks simultaneously | 🧠 |
| 5:30–6:00 | ADR-007 (optimistic locking + fractional indexing vs CRDT/OT) | 🧠 |

**Done when:** a full party scenario works on the phone, and the playlist conflict tests pass.

---

## Day 6 — Playlist mobile + Control Delegation

| Time | Task | Who |
|---|---|---|
| 0:00–2:00 | Playlist mobile: list, create (visibility/license), invite, editor with drag-to-reorder, live updates, 409 → refetch + notify the user | 🤖 screens · 🧠 conflict handling |
| 2:00–4:00 | Delegation backend: `devices` (registered per app install), `delegations` (device, friend, permissions, expiry). Commands (play/pause/skip/volume) → policy check → WS push to the target device → device acks its state | 🧠 |
| 4:00–5:30 | Delegation mobile: my devices, grant/revoke control to a friend, remote-control screen, the "controlled" device obeys commands | 🤖 screens · 🧠 command handling |
| 5:30–6:00 | Tests for delegation permissions (expired, revoked, wrong device) | 🤖 |

**Done when:** a friend's phone can control your device's playback only while the delegation is valid.

---

## Day 7 — Security, observability, load testing

| Time | Task | Who |
|---|---|---|
| 0:00–1:30 | **Security pass**: IDOR tests on every endpoint (user A can't read/modify user B's data), CORS, payload limits, secrets audit. `docs/SECURITY.md`: implemented protections + identified hazards and their mitigations | 🤖 IDOR tests · 🧠 SECURITY.md |
| 1:30–3:00 | **Observability**: Loki + Grafana Alloy (log collection) + Grafana with provisioned datasources; Prometheus + FastAPI metrics; one dashboard (req/s, p50/p95/p99 latency, errors, WS connections, actions by platform/device) | 🤖 configs · 🧠 dashboard + LogQL queries |
| 3:00–5:15 | **k6 load testing**: scenarios for the 3 services (HTTP + WebSocket), ramp-up stages, thresholds; run while watching Grafana; find the breaking point | 🧠 |
| 5:15–6:00 | `docs/LOAD_TEST.md`: server specs (CPU, RAM, local/cloud), results, max concurrent users, bottleneck analysis | 🧠 |

**Done when:** the dashboard shows live traffic, and you can state "N concurrent users on this hardware, limited by X" with evidence.
**You learn:** LogQL, PromQL basics, load-testing methodology (directly reusable for ML inference APIs).

---

## Day 8 — Review: code & subject compliance

- Read **every file**, prioritizing Claude-generated code. Anything you can't explain gets rewritten or simplified.
- Run `/code-review` and `/security-review` on the codebase; fix the findings.
- Go through the subject line by line with a checklist (V.1 → V.8); every requirement maps to a feature + a test.
- Absorb any overflow from days 1–7.

## Day 9 — Review: end-to-end & docs

- Multi-device scenarios (phone + emulator, 2 accounts) for each service, including private/invited/location licenses and conflicts.
- **Clean clone test:** fresh clone → `cp .env.example .env` → `make up` → everything works.
- Rerun the load test on the final code and update the report.
- Finalize README (setup, architecture diagram, API docs link), ADRs, `AI_USAGE.md`.

## Day 10 — Review: defense rehearsal & submission

- Mock defense: Claude plays the evaluator (architecture, concurrency, security, load, "why not X?").
- Fix the weak spots that come up.
- Final check that no secrets are in git history; submit.

---

## Tooling reference

- **Backend:** Python + uv, FastAPI, SQLAlchemy 2 (async) + asyncpg, Alembic, pydantic-settings, argon2-cffi, PyJWT, google-auth, redis-py (`redis.asyncio`), httpx, structlog, pytest + pytest-asyncio, ruff.
- **Mobile:** Expo (dev build), expo-router, expo-secure-store, Expo audio module, Google Sign-In library, TanStack Query, openapi-typescript.
- **Infra:** Docker Compose, mailpit, Loki, Grafana Alloy (Promtail is EOL since March 2026), Grafana, Prometheus, k6.
- Pin exact versions at setup on Day 1 (check each library's current docs then).

## Open decisions

- [x] Platform: **cross-platform code (Android + iOS), validated on Android** (Linux dev machine). iOS testing only if a Mac / paid Apple account becomes available during the review days.
- [x] Test devices: **physical Android** (dev build, full app) + **physical iPhone occasionally via Expo Go** (everything except Google Sign-In). Day 1: confirm secure-store, audio and location work in Expo Go.
- [ ] GitHub repo created?
