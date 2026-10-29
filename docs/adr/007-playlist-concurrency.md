# ADR-007: Playlist editing with optimistic locking and fractional positions

- **Date:** 2026-10-29
- **Status:** accepted (DRAFT by Claude, to be rewritten by me)

## Context

Several people edit one playlist in real time and may move different tracks, or the same one, at the same moment (subject V.2.3). Nobody's change may be silently lost, and the order must stay consistent for everyone.

## Options considered

1. **Last write wins**: simple, but a concurrent move silently overwrites another.
2. **Pessimistic locks** held while a user edits: blocks everyone else, bad for mobile clients that disappear.
3. **Optimistic locking**: the playlist has a `version`; every write sends the version it saw; a mismatch returns **409** and the client refetches.
4. **CRDT / OT** (what Google Docs does): no rejected edits, but complex to build and to explain.

For the order itself: integer positions need renumbering every track between the old and new place; **fractional positions** need one row update (the midpoint between the new neighbours).

## Decision

Optimistic locking on the whole playlist + float fractional positions, with a renumbering (1, 2, 3…) when a gap gets under 1e-9.

`UPDATE playlists SET version = version + 1 WHERE id = :id AND version = :expected RETURNING version`: the row lock makes concurrent writers wait, and when the first commits, Postgres re-checks the `WHERE` for the next one, which fails → 409.

## Why

- Correct by construction, and simple enough to explain line by line.
- A playlist is edited by a few people at human speed: conflicts are rare and a refetch + retry is cheap.
- Fractional positions keep a move to one row (tested: only the moved row changes).

## Consequences

- Tested: two users moving different tracks or the same track at once → one 200, one 409, nothing lost or duplicated; 10 simultaneous adds with the same version → 1 success.
- Under heavy contention (load test: every editor on one playlist) ~6 % of moves get a 409. The app reapplies the user's move on the fresh version.
- Floats lose precision after ~50 halvings of the same gap: the renumbering handles it (tested with 70 moves).
- A CRDT would avoid rejections, at a cost this project doesn't need.
