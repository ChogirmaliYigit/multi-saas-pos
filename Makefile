# Common operations. `make help` lists them.
.DEFAULT_GOAL := help
SHELL := /bin/bash

COMPOSE := docker compose

.PHONY: help
help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'

# --- local development -----------------------------------------------------

.PHONY: dev-db
dev-db: ## Start Postgres + Redis for local development
	$(COMPOSE) up -d postgres redis

.PHONY: migrate
migrate: ## Apply migrations (host, against the dev database)
	cd backend && PYTHONPATH=. .venv/bin/alembic upgrade head

.PHONY: seed
seed: ## Seed plans and the platform admin
	cd backend && PYTHONPATH=. .venv/bin/python -m app.db.seed

.PHONY: seed-demo
seed-demo: ## Seed a demo catalog: make seed-demo SLUG=corner
	cd backend && PYTHONPATH=. .venv/bin/python -m app.db.seed_demo $(or $(SLUG),corner)

.PHONY: api
api: ## Run the API on the host with reload
	cd backend && PYTHONPATH=. .venv/bin/uvicorn app.main:app --reload --port 8000

.PHONY: worker
worker: ## Run a Celery worker on the host
	cd backend && PYTHONPATH=. .venv/bin/celery -A app.worker.celery_app.celery_app worker --loglevel=info

.PHONY: web
web: ## Run the Next.js dev server
	cd frontend && npm run dev

# --- quality ---------------------------------------------------------------

.PHONY: test
test: ## Run the backend test suite
	cd backend && PYTHONPATH=. .venv/bin/pytest -q

.PHONY: lint
lint: ## Lint and format-check both sides
	cd backend && .venv/bin/ruff check app tests alembic && .venv/bin/ruff format --check app tests alembic
	cd frontend && npm run lint && npx tsc --noEmit && npx prettier --check "src/**/*.{ts,tsx,css}"

.PHONY: fmt
fmt: ## Auto-format both sides
	cd backend && .venv/bin/ruff check app tests alembic --fix && .venv/bin/ruff format app tests alembic
	cd frontend && npx prettier --write "src/**/*.{ts,tsx,css}"

.PHONY: check
check: lint test ## Everything CI would run

# --- deployment ------------------------------------------------------------

.PHONY: build
build: ## Build production images
	$(COMPOSE) build

.PHONY: up
up: ## Start the stack (API on a VPS; frontend on Vercel)
	$(COMPOSE) up -d

.PHONY: up-all
up-all: ## Start the stack including the self-hosted frontend
	$(COMPOSE) --profile selfhost up -d

.PHONY: down
down: ## Stop the stack, keeping volumes
	$(COMPOSE) down

.PHONY: logs
logs: ## Tail logs: make logs S=api
	$(COMPOSE) logs -f $(or $(S),)

.PHONY: ps
ps: ## Service status
	@$(COMPOSE) ps --format 'table {{.Service}}\t{{.State}}\t{{.Health}}\t{{.Ports}}'

.PHONY: deploy
deploy: ## Build, migrate and roll out, with rollback on failure
	./deployment/scripts/deploy.sh

.PHONY: backup
backup: ## Dump and verify the database
	./deployment/scripts/backup.sh

.PHONY: shell-db
shell-db: ## psql as the schema owner
	$(COMPOSE) exec postgres psql -U $${POSTGRES_ADMIN_USER:-pos} -d $${POSTGRES_DB:-pos}

.PHONY: clean
clean: ## Stop everything and DELETE the volumes
	@read -rp "This destroys the database. Type 'yes': " ok; [[ "$$ok" == "yes" ]] || exit 1
	$(COMPOSE) down -v
