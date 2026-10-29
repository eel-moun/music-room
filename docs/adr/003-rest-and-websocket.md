# ADR-003: REST for commands, WebSocket + Redis pub/sub for realtime

- **Date:** 2026-10-29
- **Status:** accepted (DRAFT by Claude, to be rewritten by me)

## Context

Votes, playlist edits and control delegation must show up on every connected phone within a second. The API runs several uvicorn workers, and each worker only knows the WebSockets connected to it.

## Options considered

1. **Polling:** simplest, but wasteful and slow to feel "live".
2. **Server-Sent Events:** one-way and simple, but less common in React Native.
3. **WebSocket per worker, no broker:** only clients on the same worker see each other's events.
4. **WebSocket + Redis pub/sub:** each worker subscribes once and forwards events to its own sockets.
5. **WebSocket + Redis Streams:** keeps history and allows replay, at the price of more code.

## Decision

Clients send commands over REST and receive state over a WebSocket per room. Workers share events through Redis pub/sub (`app/realtime/rooms.py`). Envelope: `{type, room, seq, payload}`, with `seq` from a per-room Redis counter.

## Why

- REST keeps validation, authorization (`app/policies/`) and status codes (409, 403) in one place; the socket only pushes.
- Pub/sub is enough because the server is the source of truth: a client that missed events refetches over REST.
- Proved on the 2-worker stack on 2026-10-29 (`backend/scripts/ws_spike.py`): published by one worker, delivered by the other, in both directions.

## Consequences

- Pub/sub keeps nothing: events published while Redis or a client is down are lost. Clients must refetch on reconnect and can spot gaps with `seq`.
- Tested: after a Redis restart, events in flight are lost, then the subscriber reconnects on its own within seconds.
- One Redis subscription per worker, not per socket.
