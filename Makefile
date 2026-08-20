PYTHON ?= .venv/bin/python
PIP ?= .venv/bin/pip

.PHONY: help install run run-docker stop-docker test unit load analyze triage-demo clean lint

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

install: ## Install Python dependencies
	$(PIP) install -r requirements.txt

run: ## Start the app locally (SQLite, metrics on, tracing off)
	ENABLE_TRACING=false $(PYTHON) run.py

run-docker: ## Start the full observability stack via Docker Compose
	docker compose up --build

stop-docker: ## Stop the Docker Compose stack
	docker compose down

test: ## Run a quick smoke test against a running app
	curl -fsS http://localhost:8010/health | $(PYTHON) -m json.tool
	curl -fsS -X POST http://localhost:8010/chat \
		-H "Content-Type: application/json" \
		-d '{"prompt":"smoke test"}' | $(PYTHON) -m json.tool
	curl -fsS http://localhost:8010/api/stats | $(PYTHON) -m json.tool
	curl -fsS http://localhost:8010/api/triage | $(PYTHON) -m json.tool

unit: ## Run deterministic incident-classification tests
	$(PYTHON) -m pytest -q

load: ## Run the k6 load test (requires k6 installed)
	k6 run k6/load-test.js

analyze: ## Run the observability analysis report
	$(PYTHON) scripts/analyze.py

analyze-24h: ## Run the observability report for the last 24h
	$(PYTHON) scripts/analyze.py --hours 24

triage-demo: ## Classify the captured degraded-service example
	$(PYTHON) scripts/triage.py examples/degraded-stats.json

lint: ## Syntax-check all Python files
	$(PYTHON) -m compileall app scripts

clean: ## Remove local data (DB, logs, pid)
	rm -f data/*.db data/*.db-journal data/*.log data/*.err data/*.pid
