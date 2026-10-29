"""Prometheus metrics. With several uvicorn workers, each worker writes its samples
to PROMETHEUS_MULTIPROC_DIR and /metrics aggregates them (otherwise a scrape would
only see the one worker that answered it)."""

import os

from prometheus_client import (
    CONTENT_TYPE_LATEST,
    REGISTRY,
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
    multiprocess,
)

HTTP_REQUESTS = Counter(
    "http_requests_total", "HTTP requests", ["method", "route", "status", "platform"]
)
HTTP_LATENCY = Histogram(
    "http_request_duration_seconds",
    "HTTP request latency",
    ["method", "route"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5),
)
WS_CONNECTIONS = Gauge("ws_connections", "Open WebSocket connections", multiprocess_mode="livesum")
WS_EVENTS = Counter("ws_events_delivered_total", "Realtime events sent to sockets")


def render() -> tuple[bytes, str]:
    if "PROMETHEUS_MULTIPROC_DIR" in os.environ:
        registry = CollectorRegistry()
        multiprocess.MultiProcessCollector(registry)
    else:
        registry = REGISTRY
    return generate_latest(registry), CONTENT_TYPE_LATEST
