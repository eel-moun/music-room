# ADR-002: Music provider

- **Date:** 2026-10-29
- **Status:** accepted (DRAFT by Claude, to be rewritten by me)

## Context

The app must search and play real tracks. The provider must accept new developer apps, allow enough test users for a defense, and give full-length streams.

## Options considered

1. **Spotify:** best catalog, but development mode caps the number of users, and playback needs Premium.
2. **Deezer:** new app registrations are closed.
3. **Jamendo:** open API with a client id, Creative Commons catalog. Considered as fallback, then dropped to keep one provider.
4. **Audius:** open API, full streams, search and stream work with only an `app_name` parameter (checked on 2026-10-28).

## Decision

Audius, behind a `MusicProvider` protocol (`app/music/provider.py`). We store only track references (provider, external_id, title, artist, duration, artwork), never audio.

## Why

- No user cap and no account needed to listen.
- The protocol keeps the rest of the app provider-agnostic: adding a provider is one class.

## Consequences

- Stream URLs are signed and probably short-lived: they are fetched right before playback, never stored.
- Search filters out non-streamable and gated tracks after Audius applies `limit`, so a page can be shorter than requested.
- Audius outages surface as `502`; unknown ids (Audius answers `400`) as `404`.
- How to send our API key is not verified yet; calls work without it.
