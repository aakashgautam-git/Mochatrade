# MochaTrade Crisis Command
#
# Two commands to run the whole thing:
#     make setup
#     make dev
#
# All paths here are relative on purpose: the repo may live under a directory
# whose name contains a space.

PY ?= python3.13

# ~/.npm is root-owned on this machine, which breaks installs. Use a
# project-local cache instead.
NPM := npm_config_cache=../.cache/npm npm

.DEFAULT_GOAL := help
.PHONY: help setup setup-backend setup-web dev backend web migrate seed test test-engine test-web typecheck build clean

help: ## Show available targets
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

setup: setup-backend setup-web ## Install backend + frontend dependencies
	@echo ""
	@echo "Setup complete. Run: make dev"

setup-backend: ## Create the venv, install Python deps, migrate
	cd backend && $(PY) -m venv .venv
	cd backend && .venv/bin/pip install --quiet --upgrade pip
	cd backend && .venv/bin/pip install --quiet -r requirements.txt
	$(MAKE) migrate

setup-web: ## Install frontend deps
	cd web && $(NPM) install

dev: ## Run Django (:8000) and Vite (:5173) together
	@$(MAKE) -j2 backend web

backend: ## Run the Django dev server only
	cd backend && .venv/bin/python manage.py runserver 8000

web: ## Run the Vite dev server only
	cd web && $(NPM) run dev

migrate: ## Apply migrations
	cd backend && .venv/bin/python manage.py migrate

seed: ## Seed the policy and scenarios, pre-run every scenario both ways, then the demo drills
	cd backend && .venv/bin/python manage.py seed_policy
	cd backend && .venv/bin/python manage.py seed_scenarios
	cd backend && .venv/bin/python manage.py warm_runs
	cd backend && .venv/bin/python manage.py seed_demo

test: ## Run the full pytest suite
	cd backend && .venv/bin/pytest

test-engine: ## Run only the pure-Python risk engine tests
	cd backend && .venv/bin/pytest tests -k engine

test-web: ## Run the pure-function simulator tests (Node)
	cd web && $(NPM) test

typecheck: ## TypeScript strict check
	cd web && $(NPM) run typecheck

build: ## Production build of the web app
	cd web && $(NPM) run build

clean: ## Remove venv, node_modules, caches and the local database
	rm -rf backend/.venv backend/db.sqlite3 backend/.pytest_cache
	rm -rf web/node_modules web/dist .cache
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
