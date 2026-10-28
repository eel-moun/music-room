.DEFAULT_GOAL := help
COMPOSE := docker compose
API := $(COMPOSE) exec api

.PHONY: help env up down restart logs ps migrate revision test lint format shell psql redis-cli mobile-install mobile

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

mobile-install: ## Install mobile dependencies
	cd mobile && npm install

mobile: ## Start the Expo dev server
	cd mobile && npx expo start
