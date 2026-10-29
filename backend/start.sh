#!/bin/sh
# Production entrypoint: migrate, then serve with several workers.
set -e

# Each worker writes its metrics here; /metrics aggregates them. Start clean.
rm -rf "$PROMETHEUS_MULTIPROC_DIR"
mkdir -p "$PROMETHEUS_MULTIPROC_DIR"

alembic upgrade head

exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers "${WEB_WORKERS:-2}"
