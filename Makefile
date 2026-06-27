SHELL := /bin/sh

UV_CACHE_DIR ?= /tmp/uv-cache
UV ?= UV_CACHE_DIR=$(UV_CACHE_DIR) uv
PYTHON ?= $(UV) run --extra bot python
PYTEST ?= $(UV) run --extra bot --with pytest --with pytest-asyncio pytest

DATASET ?= dataset/run_example.json
LIMIT ?= 10
CASE_ID ?=

RUN_OUTPUT ?= autoeval/run/results/run_result_agent_latest.json
REPLAY_OUTPUT ?= autoeval/run/results/run_result_replay_latest.json
RUN_RESULT ?= $(RUN_OUTPUT)
EVAL_OUTPUT ?= autoeval/eval/results/eval_result_latest.json
CRITERIA ?= all
EVAL_MAX_TOKENS ?= 3000
EVAL_RESULT ?= $(EVAL_OUTPUT)
REPORT_OUTPUT ?= autoeval/metrics/results/metrics_latest.xlsx

CASE_ARGS = $(foreach id,$(CASE_ID),--case-id $(id))
LIMIT_ARGS = $(if $(LIMIT),--limit $(LIMIT),)

.PHONY: help install bot mcp rag-web test format \
	docker-up docker-down docker-logs \
	autoeval-run autoeval-replay autoeval-eval autoeval-report \
	autoeval-10 autoeval-full autoeval-replay-10 autoeval-replay-full

help:
	@echo "Common commands:"
	@echo "  make install                 Install dependencies with bot+mcp extras"
	@echo "  make bot                     Run Telegram bot locally"
	@echo "  make mcp                     Run MCP server locally"
	@echo "  make rag-web                 Run RAG web UI locally"
	@echo "  make test                    Run unit tests"
	@echo "  make format                  Run black on project code"
	@echo ""
	@echo "Docker:"
	@echo "  make docker-up               docker compose up --build"
	@echo "  make docker-down             docker compose down"
	@echo "  make docker-logs             docker compose logs -f"
	@echo ""
	@echo "Autoeval:"
	@echo "  make autoeval-run            Run agent benchmark, default LIMIT=10"
	@echo "  make autoeval-eval           Eval RUN_RESULT, default RUN_RESULT=$(RUN_OUTPUT)"
	@echo "  make autoeval-report         Build Excel metrics report from EVAL_RESULT"
	@echo "  make autoeval-10             Run agent benchmark + eval on 10 samples"
	@echo "  make autoeval-full           Run agent benchmark + eval + report on all samples"
	@echo "  make autoeval-replay         Replay dataset fixtures, default LIMIT=10"
	@echo "  make autoeval-replay-10      Replay + eval on 10 samples"
	@echo "  make autoeval-replay-full    Replay + eval + report on all samples"
	@echo ""
	@echo "Overrides:"
	@echo "  make autoeval-10 LIMIT=20"
	@echo "  make autoeval-run CASE_ID='2 6 45' LIMIT="
	@echo "  make autoeval-eval RUN_RESULT=autoeval/run/results/run_result_agent_10.json"
	@echo "  make autoeval-report EVAL_RESULT=autoeval/eval/results/eval_result_agent_10.json"

install:
	$(UV) sync --extra bot --extra mcp

bot:
	$(PYTHON) -m chat_bot.bot

mcp:
	$(PYTHON) -m chat_bot.mcp_server.server

rag-web:
	$(PYTHON) -m chat_bot.rag.web

test:
	$(PYTEST) tests/unit -q

format:
	$(UV) run --extra bot --with black black chat_bot autoeval tests

docker-up:
	docker compose up --build

docker-down:
	docker compose down

docker-logs:
	docker compose logs -f

autoeval-run:
	$(PYTHON) -m autoeval.run.runner \
		--mode agent \
		--dataset $(DATASET) \
		$(LIMIT_ARGS) \
		$(CASE_ARGS) \
		--output $(RUN_OUTPUT)

autoeval-replay:
	$(PYTHON) -m autoeval.run.runner \
		--mode replay \
		--dataset $(DATASET) \
		$(LIMIT_ARGS) \
		$(CASE_ARGS) \
		--output $(REPLAY_OUTPUT)

autoeval-eval:
	AI_EVAL_MAX_TOKENS=$(EVAL_MAX_TOKENS) $(PYTHON) -m autoeval.eval.runner \
		--run-result $(RUN_RESULT) \
		--dataset $(DATASET) \
		--criteria $(CRITERIA) \
		$(CASE_ARGS) \
		--output $(EVAL_OUTPUT)

autoeval-report:
	$(PYTHON) -m autoeval.metrics.excel_report \
		--eval-result $(EVAL_RESULT) \
		--output $(REPORT_OUTPUT)

autoeval-10:
	$(MAKE) autoeval-run LIMIT=10 RUN_OUTPUT=autoeval/run/results/run_result_agent_10.json
	$(MAKE) autoeval-eval RUN_RESULT=autoeval/run/results/run_result_agent_10.json EVAL_OUTPUT=autoeval/eval/results/eval_result_agent_10.json
	$(MAKE) autoeval-report EVAL_RESULT=autoeval/eval/results/eval_result_agent_10.json REPORT_OUTPUT=autoeval/metrics/results/metrics_agent_10.xlsx

autoeval-full:
	$(MAKE) autoeval-run LIMIT= RUN_OUTPUT=autoeval/run/results/run_result_agent_full_complex.json
	$(MAKE) autoeval-eval RUN_RESULT=autoeval/run/results/run_result_agent_full_complex.json EVAL_OUTPUT=autoeval/eval/results/eval_result_agent_full_complex.json EVAL_MAX_TOKENS=5000
	$(MAKE) autoeval-report EVAL_RESULT=autoeval/eval/results/eval_result_agent_full_complex.json REPORT_OUTPUT=autoeval/metrics/results/metrics_agent_full_complex.xlsx

autoeval-replay-10:
	$(MAKE) autoeval-replay LIMIT=10 REPLAY_OUTPUT=autoeval/run/results/run_result_replay_10.json
	$(MAKE) autoeval-eval RUN_RESULT=autoeval/run/results/run_result_replay_10.json EVAL_OUTPUT=autoeval/eval/results/eval_result_replay_10.json
	$(MAKE) autoeval-report EVAL_RESULT=autoeval/eval/results/eval_result_replay_10.json REPORT_OUTPUT=autoeval/metrics/results/metrics_replay_10.xlsx

autoeval-replay-full:
	$(MAKE) autoeval-replay LIMIT= REPLAY_OUTPUT=autoeval/run/results/run_result_replay_full_complex.json
	$(MAKE) autoeval-eval RUN_RESULT=autoeval/run/results/run_result_replay_full_complex.json EVAL_OUTPUT=autoeval/eval/results/eval_result_replay_full_complex.json EVAL_MAX_TOKENS=5000
	$(MAKE) autoeval-report EVAL_RESULT=autoeval/eval/results/eval_result_replay_full_complex.json REPORT_OUTPUT=autoeval/metrics/results/metrics_replay_full_complex.xlsx
