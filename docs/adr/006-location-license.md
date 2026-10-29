# ADR-006: Location + time license, and the spoofable GPS hazard

- **Date:** 2026-10-29
- **Status:** accepted (DRAFT by Claude, to be rewritten by me)

## Context

A Track Vote license must let only "people located in a specific place at a specific time" vote (subject V.2.1).

## Decision

- **Time**: the event stores `starts_at` / `ends_at` (timezone-aware); the check uses the **server clock**, never the phone's.
- **Place**: the event stores a center and a radius (10 m – 50 km). The app sends its GPS position with each vote/suggestion; the server computes the haversine distance (`app/policies/geo.py`).
- The owner can always vote. Both conditions are enforced by a DB check constraint (all five fields required for this license).

## Known hazard

The position is **declared by the client**. Fake-GPS apps (or a modified client) can claim to be at the venue. The server can't prove where a phone is.

Practical mitigations, not implemented:
- Device attestation (Play Integrity / App Attest) to refuse modified clients and mock locations.
- Proof of presence: a rotating code or QR shown on the host's screen, or a BLE beacon at the venue.

## Consequences

The license stops honest users outside the area, not a determined cheater. This is stated in SECURITY.md and will be said in the defense.
