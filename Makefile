.PHONY: help install install-ui lint format typecheck test test-unit test-integration run-api run-streamlit run-gradio clean

VENV ?= venv
PYTHON ?= python3
PIP := $(VENV)/bin/pip
PYTEST := $(VENV)/bin/pytest
RUFF := $(VENV)/bin/ruff
MYPY := $(VENV)/bin/mypy
SEMCOD_API_BIN := $(VENV)/bin/semcod-api
SEMCOD_STREAMLIT_BIN := $(VENV)/bin/semcod-streamlit
SEMCOD_GRADIO_BIN := $(VENV)/bin/semcod-gradio
API_HOST ?= 0.0.0.0
API_PORT ?= 8000

.DEFAULT_GOAL := help

GREEN := \033[32m
CYAN := \033[36m
PURPLE := \033[35m
YELLOW := \033[33m
RESET := \033[0m

help:
	@printf "\n${CYAN}🚀  semcod Makefile Commands${RESET}\n"
	@printf "${PURPLE}────────────────────────────────────${RESET}\n"
	@printf "${GREEN}🧱  make install          ${RESET}- create .venv and install runtime + dev deps\n"
	@printf "${GREEN}🧱  make install-ui       ${RESET}- install with UI extras (Streamlit/Gradio)\n"
	@printf "${GREEN}🧹  make clean            ${RESET}- remove __pycache__ and stray pyc files\n"
	@printf "${GREEN}🧪  make test             ${RESET}- run full pytest suite\n"
	@printf "${GREEN}🧪  make test-unit        ${RESET}- run unit tests only (excludes integration)\n"
	@printf "${GREEN}🧪  make test-integration ${RESET}- run integration tests (no external services)\n"
	@printf "${GREEN}✨  make lint             ${RESET}- lint with Ruff\n"
	@printf "${GREEN}✨  make format           ${RESET}- auto-format with Ruff\n"
	@printf "${GREEN}🧠  make typecheck        ${RESET}- static type checking via mypy\n"
	@printf "${GREEN}🌐  make run-api          ${RESET}- launch FastAPI (override host/port via API_HOST/API_PORT)\n"
	@printf "${GREEN}📊  make run-streamlit    ${RESET}- start Streamlit frontend\n"
	@printf "${GREEN}🎛️  make run-gradio       ${RESET}- start Gradio UI\n"
	@printf "\n${YELLOW}Tip:${RESET} export SEMCOD_CONFIG_PATH or edit semcod_settings.toml before running services.\n\n"

$(VENV)/bin/python:
	$(PYTHON) -m venv $(VENV)
	$(PIP) install --upgrade pip wheel setuptools

install: $(VENV)/bin/python
	$(PIP) install -e .[dev]

install-ui: $(VENV)/bin/python
	$(PIP) install -e .[dev,ui]

lint: $(RUFF)
	$(RUFF) check src tests

format: $(RUFF)
	$(RUFF) format src tests

typecheck: $(MYPY)
	$(MYPY) src

test: $(PYTEST)
	$(PYTEST)

test-unit: $(PYTEST)
	$(PYTEST) tests -k "not integration"

test-integration: $(PYTEST)
	$(PYTEST) tests/integration

run-api: $(SEMCOD_API_BIN)
	SEMCOD_API_HOST=$(API_HOST) SEMCOD_API_PORT=$(API_PORT) $(SEMCOD_API_BIN)

run-streamlit: $(SEMCOD_STREAMLIT_BIN)
	$(SEMCOD_STREAMLIT_BIN)

run-gradio: $(SEMCOD_GRADIO_BIN)
	$(SEMCOD_GRADIO_BIN)

clean:
	find . -name "__pycache__" -type d -prune -exec rm -rf {} +; \
	find . -name "*.pyc" -delete
