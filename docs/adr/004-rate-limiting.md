# ADR-004: Fixed-window rate limiting in Redis

- **Date:** 2026-10-29
- **Status:** accepted (DRAFT by Claude, to be rewritten by me)

## Context

Auth endpoints must resist brute force (subject V.6). The API runs several workers, so counters must be shared: in-process counters would give each worker its own budget.

## Options considered

1. **Fixed window** (`INCR` + `EXPIRE NX`): one key per (action, subject), reset when the TTL ends. Two commands, O(1) memory. Allows up to 2× the limit across a window boundary.
2. **Sliding log** (sorted set of timestamps): exact, but memory grows with the limit and every hit is `ZADD` + `ZREMRANGEBYSCORE` + `ZCARD`.
3. **Token bucket** (Lua script): smooth bursts, needs a script to stay atomic.

## Decision

Fixed window, in one `MULTI` pipeline (`INCR`, `EXPIRE … NX`, `TTL`), keyed per IP and per account (`app/core/ratelimit.py`).

## Why

- The 2× edge burst is irrelevant at these limits (10 guesses per 15 min vs 20 still makes password guessing hopeless).
- Smallest code, easiest to explain, and `EXPIRE NX` (Redis 7+) makes "start the window on the first hit" atomic.

## Consequences

- Per-account limits let an attacker lock a victim out for 15 min (documented in SECURITY.md).
- All load-test traffic comes from one IP, so k6 uses pre-issued tokens instead of logging in.
