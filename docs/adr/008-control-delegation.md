# ADR-008: Control delegation, per-device licenses and realtime commands

- **Date:** 2026-10-29
- **Status:** accepted (DRAFT by Claude, to be rewritten by me)

## Context

A user gives control of their music to friends, with a license specific to each device (subject V.2.2).

## Decision

- **Device** = one app install, registered on first launch (its id lives in secure storage).
- **Delegation** = (device, friend, permissions, optional expiry, revoked_at). Permissions are `playback` (play, pause, next, previous, play a track or playlist) and `volume`. One active delegation per (device, friend), enforced by a partial unique index.
- A command is a REST call: the policy checks owner, or a delegation that is not revoked, not expired, has the permission, **and the two users are still friends**. It is then pushed to the device's room over WebSocket. The device plays it and reports its state (`PUT /devices/{id}/state`), which is relayed to the controllers.
- Device state is ephemeral: Redis with a 24 h TTL, not Postgres.

## Why

- REST for commands keeps one authorization path and real HTTP status codes; the socket only delivers.
- Re-checking friendship on every command means unfriending revokes control instantly, without a background job.
- Revoking kicks the friend's sockets out of the device room on every worker (`rooms.kick`).

## Consequences

- If the device is offline, the command is lost (pub/sub keeps nothing). The controller sees no state change and can resend. A command queue would fix this if needed.
- Tested: no delegation, revoked, expired, missing permission, unfriended, wrong device.
