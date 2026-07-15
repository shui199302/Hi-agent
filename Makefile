SHELL := /bin/bash
export PATH := $(CURDIR)/.tools/bin:$(CURDIR)/.tools/node/bin:$(PATH)
export UV_CACHE_DIR := $(CURDIR)/.tools/uv-cache
export UV_PYTHON_INSTALL_DIR := $(CURDIR)/.tools/python
export PLAYWRIGHT_BROWSERS_PATH := $(CURDIR)/.tools/playwright
UV := $(shell command -v uv 2>/dev/null || printf '%s' '$(CURDIR)/.tools/bin/uv')
PNPM := $(shell command -v pnpm 2>/dev/null || printf '%s' '$(CURDIR)/.tools/bin/pnpm')

.PHONY: install install-backend install-web dev start stop verify backend-test web-test build doctor compose-check real-rag-test

install: install-backend install-web build

install-backend:
	$(UV) sync --project backend --all-extras --dev
	$(UV) sync --project mcp_servers --dev

install-web:
	$(PNPM) --dir web install --frozen-lockfile
	$(PNPM) --dir web exec playwright install chromium

dev:
	./scripts/dev.sh

start:
	./start.command

stop:
	./stop.command

backend-test:
	cd backend && .venv/bin/ruff check src tests && .venv/bin/mypy src && .venv/bin/pytest

web-test:
	$(PNPM) --dir web lint && $(PNPM) --dir web test -- --run && $(PNPM) --dir web test:e2e

build:
	$(PNPM) --dir web build

doctor:
	./scripts/doctor.sh

compose-check:
	docker compose --env-file deploy/vllm.env.example -f deploy/vllm-compose.yml config --quiet
	docker compose -f deploy/app-compose.yml config --quiet

real-rag-test:
	$(UV) run --project backend --no-sync python scripts/real_rag_smoke.py

verify: backend-test web-test build compose-check doctor
	PYTHONPATH=mcp_servers/src backend/.venv/bin/pytest -q mcp_servers/tests
	./scripts/smoke.sh
	$(MAKE) real-rag-test
