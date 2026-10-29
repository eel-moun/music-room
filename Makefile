.DEFAULT_GOAL := help
COMPOSE := docker compose
API := $(COMPOSE) exec api

.PHONY: help env up down restart logs ps migrate revision test lint format shell psql redis-cli prod-up prod-down prod-logs obs-up seed check-realtime loadtest-tokens loadtest mobile-api mobile-check mobile-install mobile

help: ## Show available targets
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

env: ## Create .env from .env.example if missing
	@test -f .env || (cp .env.example .env && echo "Created .env — fill in the secrets")

up: env ## Build and start all services
	$(COMPOSE) up -d --build

down: ## Stop all services
	$(COMPOSE) down

restart: ## Restart the API
	$(COMPOSE) restart api

logs: ## Follow API logs
	$(COMPOSE) logs -f api

ps: ## List running services
	$(COMPOSE) ps

migrate: ## Apply database migrations
	$(API) uv run alembic upgrade head

revision: ## Create a migration: make revision m="message"
	$(API) uv run alembic revision --autogenerate -m "$(m)"

test: ## Run backend tests
	$(API) uv run pytest

lint: ## Lint and check formatting
	$(API) uv run ruff check .
	$(API) uv run ruff format --check .

format: ## Auto-format backend code
	$(API) uv run ruff format .
	$(API) uv run ruff check --fix .

shell: ## Shell inside the API container
	$(API) bash

psql: ## Open psql on the database
	$(COMPOSE) exec postgres sh -c 'psql -U $$POSTGRES_USER -d $$POSTGRES_DB'

redis-cli: ## Open redis-cli
	$(COMPOSE) exec redis redis-cli

PROD := docker compose -f docker-compose.prod.yml
OBS := $(PROD) -f docker-compose.observability.yml
# Alloy reads container logs from the Docker socket (rootless Docker: /run/user/<uid>/docker.sock).
export DOCKER_SOCK ?= $(shell docker context inspect --format '{{.Endpoints.docker.Host}}' 2>/dev/null | sed 's|unix://||')

prod-up: ## Start the production-like stack (needs .env.prod)
	@test -f .env.prod || (echo "Missing .env.prod — copy .env.example and set real secrets" && exit 1)
	$(PROD) up -d --build

prod-down: ## Stop the production-like stack (and observability, if running)
	$(OBS) down

obs-up: prod-up ## Prod stack + Loki/Alloy/Prometheus/Grafana (http://localhost:3000)
	$(OBS) up -d

seed: ## Create verified load-test users in the prod stack: make seed n=500
	$(PROD) exec api python -m scripts.seed --users $(or $(n),200)

check-realtime: ## End-to-end realtime check across the 2 prod workers (needs make seed)
	cd backend && uv run python scripts/check_realtime.py

loadtest-tokens: ## Seed users and write their access tokens for k6 (valid 15 min)
	$(PROD) exec -T api python -m scripts.seed --users $(or $(n),200) --tokens > loadtest/tokens.json

# --user root: rootless Docker maps it to you, so k6 can write loadtest/results.
K6 := docker run --rm -i --user root --network musicroom-prod_default -v $(CURDIR)/loadtest:/scripts grafana/k6:1.8.2

loadtest: ## Run a k6 scenario on the prod stack: make loadtest s=stress args="-e PEAK=3000"
	$(K6) run -e API=http://api:8000 $(args) --summary-export /scripts/results/$(or $(s),mixed).json /scripts/$(or $(s),mixed).js

prod-logs: ## Follow production API logs
	$(PROD) logs -f api

NODE := docker run --rm -i --user root -v $(CURDIR)/mobile:/app -w /app node:24-bookworm-slim

mobile-api: ## Regenerate the app's API types from the backend's OpenAPI (needs make up)
	$(API) uv run python -c "import json; from app.main import app; print(json.dumps(app.openapi(), indent=1))" > mobile/openapi.json
	$(NODE) npx -y openapi-typescript@7.13.0 openapi.json -o src/api/schema.d.ts

mobile-check: ## Typecheck and lint the app (in Docker, no local Node needed)
	$(NODE) sh -c "npx tsc --noEmit && npx expo lint"

mobile-install: ## Install mobile dependencies
	cd mobile && npm install

mobile: ## Start the Expo dev server
	cd mobile && npx expo start
