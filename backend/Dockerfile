FROM python:3.13-slim

COPY --from=ghcr.io/astral-sh/uv:0.10.12 /uv /uvx /bin/

WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH="/opt/venv/bin:$PATH" \
    PROMETHEUS_MULTIPROC_DIR=/tmp/prometheus

# Install dependencies first (cached layer), then the app code
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project

COPY . .
RUN uv sync --frozen && mkdir -p "$PROMETHEUS_MULTIPROC_DIR"

# Not root: a compromised process can't touch the image or the venv.
RUN useradd --system --uid 10001 app && chown -R app /tmp/prometheus
USER app

EXPOSE 8000
CMD ["./start.sh"]
