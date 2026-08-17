# Thin command mapping for local development, verification, and evaluation.

SHELL := /bin/sh
.DEFAULT_GOAL := help

UV ?= uv
NPM ?= npm
PYTHON_RUN := $(UV) run python

HOST ?= 127.0.0.1
PORT ?= 8000
IMAGE ?= ecom-ops-agent
ARGS ?=
EXP_ID ?=
VARIANT ?= A_baseline

.PHONY: help install cli api frontend-dev frontend-build lint typecheck test check schema-export \
	eval-dataset-info eval-run eval-l1 eval-l2 eval-fixtures eval-compare retrieval-eval experiment \
	reconcile docker-build

help: ## Show available commands
	@awk 'BEGIN {FS = ":.*## "} /^[a-zA-Z0-9_-]+:.*## / {printf "  %-18s %s\n", $$1, $$2}' $(MAKEFILE_LIST)

install: ## Install locked Python and frontend dependencies
	$(UV) sync --frozen
	$(NPM) --prefix frontend ci

cli: ## Start the interactive CLI (requires configured model credentials)
	$(PYTHON_RUN) main.py

api: ## Start the FastAPI development server (HOST/PORT are overridable)
	$(UV) run uvicorn src.api:app --reload --host $(HOST) --port $(PORT)

frontend-dev: ## Start the Vite development server
	$(NPM) --prefix frontend run dev

frontend-build: ## Type-check and build the frontend
	$(NPM) --prefix frontend run build

lint: ## Check Python lint and formatting
	$(UV) run ruff check .
	$(UV) run ruff format --check .

typecheck: ## Check Python types with Pyright
	$(UV) run pyright

test: ## Run deterministic Python tests with non-secret placeholder keys
	LLM_API_KEY=test-only EMBED_API_KEY=test-only $(PYTHON_RUN) -m unittest discover -s tests

check: lint typecheck test frontend-build ## Run the full deterministic quality gate

schema-export: ## Regenerate committed JSON Schema snapshots
	$(PYTHON_RUN) -m src.contracts.export_schemas

# The following evaluation targets can call remote models and incur API cost.
eval-dataset-info: ## Print current eval-case count, buckets, and SHA-256 (no model call)
	$(PYTHON_RUN) scripts/eval_dataset_info.py

eval-run: ## Generate evaluation answers and audit artifacts
	$(PYTHON_RUN) -m src.eval.answer_runner

eval-l1: ## Score L1 tool routing from existing evaluation artifacts
	$(PYTHON_RUN) -m src.eval.judge

eval-l2: ## Score L2 answer quality (non-deterministic; use N>=4 for decisions)
	$(PYTHON_RUN) -m src.eval.l2.judge

eval-fixtures: ## Run the L2 judge fixture regression
	$(PYTHON_RUN) -m src.eval.l2.fixtures

eval-compare: ## Compare single-Agent and Supervisor evaluation paths
	$(PYTHON_RUN) -m src.eval.compare

retrieval-eval: ## Evaluate FAQ retrieval (requires embedding credentials)
	$(PYTHON_RUN) -m src.eval.retrieval

experiment: ## Run experiment harness; pass CLI flags through ARGS="--name ..."
	$(PYTHON_RUN) -m src.experiment.runner $(ARGS)

reconcile: ## Reconcile defects for EXP_ID; optionally set VARIANT
	@test -n "$(EXP_ID)" || { echo "EXP_ID is required (for example: make reconcile EXP_ID=<id>)" >&2; exit 2; }
	$(PYTHON_RUN) -m src.eval.reconcile "$(EXP_ID)" "$(VARIANT)"

docker-build: ## Build the application image; override with IMAGE=<name:tag>
	docker build -t $(IMAGE) .
