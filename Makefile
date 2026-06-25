.PHONY: help install run run-docker stop-docker test load analyze clean lint

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

install: ## Install Python dependencies
	pip install -r requirements.txt

run: ## Start the app locally (SQLite, metrics on, tracing off)
	ENABLE_TRACING=false python run.py

run-docker: ## Start the full observability stack via Docker Compose
	docker compose up --build

stop-docker: ## Stop the Docker Compose stack
	docker compose down

test: ## Run a quick smoke test against a running app
	curl -fsS http://localhost:8010/health | python -m json.tool
	curl -fsS -X POST http://localhost:8010/chat \
		-H "Content-Type: application/json" \
		-d '{"prompt":"smoke test"}' | python -m json.tool
	curl -fsS http://localhost:8010/api/stats | python -m json.tool

load: ## Run the k6 load test (requires k6 installed)
	k6 run k6/load-test.js

analyze: ## Run the observability analysis report
	python scripts/analyze.py

analyze-24h: ## Run the observability report for the last 24h
	python scripts/analyze.py --hours 24

lint: ## Syntax-check all Python files
	python -m compileall app scripts

clean: ## Remove local data (DB, logs, pid)
	rm -f data/*.db data/*.db-journal data/*.log data/*.err data/*.pid
