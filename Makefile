PY ?= $(shell command -v python3 >/dev/null 2>&1 && echo python3 || echo python)
PIP := $(PY) -m pip
VENV ?= .venv

# Directories
PKG := app
TEST_DIR := tests

.PHONY: setup venv precommit run test test-unit test-integration test-contract \
        test-property test-e2e fmt lint type docker up down cov check ci clean

venv:
	$(PY) -m venv $(VENV)

setup: venv
	. $(VENV)/bin/activate; $(PIP) install --upgrade pip
	. $(VENV)/bin/activate; $(PIP) install -e .[dev]
	. $(VENV)/bin/activate; pre-commit install

precommit:
	. $(VENV)/bin/activate; pre-commit run --all-files

# Run the API locally (keep your fastapi CLI if you prefer)
run:
	. $(VENV)/bin/activate; fastapi dev -e app.main:app
# or:
# run:
# 	. $(VENV)/bin/activate; uvicorn app.main:app --reload

# ---- Tests ----
test:
	. $(VENV)/bin/activate; $(PY) -m pytest -q

test-unit:
	. $(VENV)/bin/activate; $(PY) -m pytest -q $(TEST_DIR)/unit

test-integration:
	. $(VENV)/bin/activate; $(PY) -m pytest -q $(TEST_DIR)/integration

test-contract:
	. $(VENV)/bin/activate; $(PY) -m pytest -q $(TEST_DIR)/contract

test-property:
	. $(VENV)/bin/activate; $(PY) -m pytest -q $(TEST_DIR)/property

test-e2e:
	. $(VENV)/bin/activate; $(PY) -m pytest -q $(TEST_DIR)/e2e

fmt:
	. $(VENV)/bin/activate; ruff format .

lint:
	. $(VENV)/bin/activate; ruff check .

type:
	. $(VENV)/bin/activate; mypy src

cov:
	. $(VENV)/bin/activate; $(PY) -m pytest \
		--cov=$(PKG) --cov-report=term-missing:skip-covered

# One-shot local quality gate
check: fmt lint type test

# CI-friendly (no formatting)
ci: lint type cov

docker:
	docker build -t equipe3-api:local .

up:
	docker compose up --build

down:
	docker compose down

clean:
	rm -rf .pytest_cache .mypy_cache .ruff_cache .coverage htmlcov
