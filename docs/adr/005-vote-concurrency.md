# ADR-005: Vote concurrency handled by the database

- **Date:** 2026-10-29
- **Status:** accepted (DRAFT by Claude, to be rewritten by me)

## Context

Many people vote at once, for the same or different tracks (subject V.2.1). Counts must be exact, a user must not vote twice for a track, and the ranking must stay consistent.

## Options considered

1. **Counter column** `votes` on the track, `UPDATE … SET votes = votes + 1`: fast, but "who voted" needs a second table anyway, and the two can drift.
2. **Check-then-insert in the app** ("has this user voted?" then INSERT): race condition between the check and the insert.
3. **One row per vote with `UNIQUE(event_id, track_id, user_id)`**, `INSERT … ON CONFLICT DO NOTHING`, ranking computed by `COUNT` at read time.
4. **Redis sorted set** as the source of truth: very fast, but votes would live outside Postgres.

## Decision

Option 3. Ranking = `votes DESC, suggested_at ASC, id`, computed by a single SQL query. The now-playing and played tracks are excluded and refuse votes (409). "Next" locks the event row (`SELECT … FOR UPDATE`).

## Why

- The unique constraint is enforced by Postgres even for simultaneous requests: no lock in the app, no race.
- Votes are idempotent (voting twice = once), which is also what a flaky mobile network needs (retries).
- The count can't drift: it's derived, never stored.

## Consequences

- Proved by tests: 50 users voting at once → exactly 50; one user sending 20 votes at once → 1; 3 tracks with overlapping voters → exact counts; 10 people suggesting the same track at once → queued once; two "next" at once → no skipped track.
- Every vote recomputes the ranking; at ~800 users this is part of the CPU cost (LOAD_TEST.md), which a Redis sorted set or coalesced broadcasts would reduce.
