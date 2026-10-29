# Security

Subject V.6: protect users, plan for malicious behavior (brute force, session theft…), identify the remaining hazards and explain the practical protections. Every row under "Implemented" points to the code and the test that proves it.

## Implemented protections

### Accounts and passwords

| Threat | Protection | Where | Test |
|---|---|---|---|
| Password database leak | argon2id (t=3, 64 MiB, p=4; ~40 ms per verification), run in a thread pool so it doesn't block the event loop | `app/core/security.py` | `test_auth.py` |
| Finding which emails have an account | Register and forgot-password give the same answer whether the email exists or not; a wrong password and an unknown email return the same error; login always runs argon2 (against a dummy hash for unknown emails), so response time doesn't leak it | `app/auth/router.py` | `test_register_existing_email_does_not_reveal_it`, `test_wrong_password_and_unknown_email_look_the_same`, `test_forgot_password_unknown_email_looks_the_same` |
| Unverified emails | Login is refused until the email is verified | `/auth/login` | `test_register_verify_login` |
| Weak passwords | 8–128 characters (the upper bound also caps argon2 cost per request) | `app/auth/schemas.py` | `test_password_length_is_enforced` |
| Brute force | Redis fixed-window limits (ADR-004), see the table below | `app/core/ratelimit.py` | `test_login_is_rate_limited_per_account`, `test_forgot_password_is_rate_limited` |

Rate limits (429 + `Retry-After`):

| Endpoint | Per IP | Per account |
|---|---|---|
| `/auth/login` | 30 / 5 min | 10 / 15 min |
| `/auth/register` | 10 / hour | — |
| `/auth/forgot-password`, `/auth/resend-verification` | 10 / hour | 3 / hour |
| `/auth/refresh` | 60 / min | — |
| `/auth/google` | 30 / 5 min | — |

### Sessions

| Threat | Protection | Where | Test |
|---|---|---|---|
| Stolen access token | JWT HS256 valid **15 min**; `type` claim checked; the secret is refused at startup in production if it's the default or under 32 characters | `app/core/security.py`, `app/core/config.py` | `test_invalid_access_token_is_rejected` |
| Stolen refresh token (session theft) | Opaque random tokens (256 bits), only their SHA-256 stored. **Rotation**: each refresh token works once. **Reuse detection**: replaying a used token revokes its whole family (attacker and victim both log in again) and logs `refresh_token_reuse_detected` | `app/auth/service.py` | `test_refresh_rotates_tokens`, `test_reused_refresh_token_revokes_the_whole_family` |
| Two refreshes racing | A single atomic `UPDATE … WHERE revoked_at IS NULL RETURNING`: only one wins | `rotate_refresh_token` | `test_concurrent_refresh_with_same_token_succeeds_once` |
| Session kept after a password leak | Password reset revokes every refresh token of the user; logout revokes the family | `/auth/reset-password`, `/auth/logout` | `test_forgot_and_reset_password`, `test_logout_revokes_refresh_token` |
| Email links reused or guessed | Random tokens, stored hashed, single use (atomic), 24 h expiry, a new request cancels the previous one | `create_email_token` / `consume_email_token` | `test_verification_token_works_once` |
| Tokens on the phone | Stored in the OS keystore (expo-secure-store: Android Keystore / iOS Keychain), never in plain storage | `mobile/src/lib/storage.ts` | — |

### Google sign-in

| Threat | Protection | Where | Test |
|---|---|---|---|
| Forged "I'm logged in as X" from the app | The Google **ID token is verified on the server**: signature, expiry, issuer, and audience = one of our client ids | `app/auth/google.py` | `test_google_invalid_token` |
| Misconfiguration silently skipping the audience check | google-auth skips the audience check when `audience=None`: we refuse (503) when no client id is configured | `verify_google_id_token` | — |
| Account takeover through a Google account with the same email | No silent merge: Google sign-in on an existing email returns 409; the owner logs in with their password and links Google themselves | `/auth/google`, `/auth/google/link` | `test_google_never_takes_over_an_existing_email`, `test_link_google_then_log_in_with_it` |
| Losing access | Unlinking Google is refused when the account has no password | `/auth/google/link` (DELETE) | `test_unlink_requires_another_login_method` |

### Access to data (IDOR)

- **All authorization rules live in `app/policies/`** as pure functions, unit-tested without a database (`test_policies.py`). Routes load the facts, ask a policy, and never improvise a check.
- Private events and playlists answer **404, not 403**, to people who can't see them, so their existence doesn't leak.
- Profiles are filtered by relation: public block for everyone, friends block for friends, private block and email for the user only.
- `test_security.py` runs **24 attacks**: user B trying every owner-only action on user A's events, playlists, devices, delegations and friendships. All are refused.
- WebSocket rooms use the **same policies** as REST (`app/realtime/access.py`). Revoking a delegation or an invite **kicks** that user's sockets out of the room on every worker (`test_kick_removes_user_on_every_worker`).

### Input and transport

| Threat | Protection |
|---|---|
| Injection (SQL) | SQLAlchemy bound parameters everywhere; `LIKE` wildcards escaped in searches (`test_search_users`) |
| Fake track metadata | Clients send only `provider` + `external_id`; title, artist and duration are fetched by the server from Audius |
| Path injection toward Audius | Track ids must match `^[A-Za-z0-9]{1,32}$` before being put in the provider URL |
| Oversized payloads | Bodies over 1 MB are refused with 413 (`test_oversized_body_rejected`); string and list lengths are capped by the schemas |
| WebSocket abuse | Token sent in the first message (not in the URL, which would end up in access logs); 10 s to authenticate or the socket closes (4401); at most 20 rooms per socket; a stalled client is dropped after 2 s instead of blocking the worker |
| Browser cross-origin calls | CORS is off unless `CORS_ORIGINS` lists origins (the mobile app doesn't need CORS) |

### Secrets and infrastructure

- Secrets only in `.env` / `.env.prod` (gitignored); `.env.example` holds placeholders only. `git ls-files` contains no `.env`.
- The production image runs as an **unprivileged user** (uid 10001).
- Production publishes only the API port: Postgres and Redis are reachable only on the internal Docker network. Dev ports and Grafana/Prometheus are bound to `127.0.0.1`.

### Logging (subject V.6)

Every request produces one JSON log line with `platform`, `device`, `app_version` (headers required on every app route, `422` without them), `user_id`, route, status, duration and client IP. The lines go to Loki and are queryable in Grafana: actions by device, by app version, 429s, refresh-token reuse. WebSocket connections and subscriptions are logged the same way.

## Identified hazards, not fully solved

| Hazard | Why it matters | Practical protection |
|---|---|---|
| **No HTTPS in the local stack** | The phone talks to the PC over plain HTTP on the LAN: someone on the same Wi-Fi can read tokens | In production, terminate TLS at a reverse proxy (Caddy / nginx + Let's Encrypt) and refuse plain HTTP; enable HSTS |
| **GPS spoofing** (Track Vote location license) | The position comes from the phone, and fake-GPS apps exist (ADR-006). The time window is safe (server clock) | Device attestation (Play Integrity / App Attest), a QR code or BLE beacon at the venue, a rotating code shown on the host's screen |
| Access token valid until it expires | A stolen access token works for up to 15 min, even after logout | Keep the TTL short; for instant revocation, keep a denylist of token ids (`jti`) in Redis |
| Account lockout through the per-account limit | An attacker can deliberately fail 10 logins to block a victim for 15 min | Progressive delays, or a CAPTCHA after N failures instead of a hard block; notify the user |
| Botnet brute force | Many IPs bypass per-IP limits | The per-account limit still caps guesses at 40 per hour per account |
| A legitimate double refresh looks like a replay | If the app sends two refreshes with the same token at once, the family is revoked | The mobile client serializes refreshes (one in-flight promise) |
| Client IP behind a proxy | Behind a reverse proxy every request has the proxy's IP, so per-IP limits would hit everyone at once | Read `X-Forwarded-For` only from a trusted proxy (uvicorn `--forwarded-allow-ips`) |
| `/metrics` on the public port | Exposes request counts per route | Serve it on an internal port or block it at the reverse proxy |
| Chunked uploads bypass the size check | The 1 MB limit reads `Content-Length` | Enforce `client_max_body_size` at the reverse proxy |
| Device headers are self-declared | Anyone can claim to be "iPhone 15" | They are used for logs only, never for authorization |
| Long-lived WebSockets | The token is checked when the socket opens, not after; making an event private doesn't kick sockets that are already subscribed (removing an invite does) | Close sockets when the access token expires; kick on visibility change |
| Dependency on Audius | An outage makes search and adding tracks fail (`502`) | Already-queued tracks keep working; possible cache of track metadata |
| Grafana admin password | Defaults to `admin` if `GRAFANA_ADMIN_PASSWORD` isn't set | It's bound to localhost; set the variable in `.env.prod` |
