# ADR-001: Backend and infrastructure stack

- **Date:** 2026-10-29
- **Status:** proposed (DRAFT by Claude, to be rewritten by me)

## Context

Solo project, 10 days (7 build + 3 review). The subject asks for a mobile app, a backend API with auto-generated docs, persistent storage, realtime collaboration, logging of every action, and a load test. My background is AI/ML/MLOps: Postgres, FastAPI, Docker, GitHub Actions and React are known; Redis, Grafana, load testing and React Native are new.

## Options considered

1. **FastAPI REST + PostgreSQL + Redis:** known core, Swagger for free, Redis covers pub/sub, rate limits and token state. More pieces to run.
2. **GraphQL (Strawberry or pg_graphql) + PostgreSQL:** flexible queries for the client, but a new paradigm to learn, harder authorization per field, and no gain for a thin "remote control" client.
3. **Firebase:** fast to start, realtime built in, but hides the backend the subject wants me to design, and locks the data model.

## Decision

FastAPI (REST + JSON) with async SQLAlchemy 2 and asyncpg, PostgreSQL as the single source of truth, Redis, Docker Compose, Loki/Alloy/Grafana + Prometheus, k6, GitHub Actions.

## Why

- Postgres gives the constraints the concurrency rules rely on (unique votes, versioned playlists, transactions).
- REST + OpenAPI gives the API docs required by the subject and a generated TypeScript client.
- Most of the stack transfers to MLOps (serving APIs, Redis, observability, load testing).

## Consequences

- Redis is a second stateful service to operate and monitor.
- Every realtime feature depends on the pub/sub layer (ADR-003).
