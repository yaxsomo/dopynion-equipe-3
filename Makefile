PY ?= $(shell command -v python3 >/dev/null 2>&1 && echo python3 || echo python)
PIP := $(PY) -m pip
VENV ?= .venv

.PHONY: setup venv precommit run test fmt lint type docker up down

venv:
	$(PY) -m venv $(VENV)

setup: venv
	. $(VENV)/bin/activate; $(PIP) install --upgrade pip
	. $(VENV)/bin/activate; $(PIP) install -e .
	. $(VENV)/bin/activate; pre-commit install

precommit:
	. $(VENV)/bin/activate; pre-commit run --all-files

run:
	. $(VENV)/bin/activate; fastapi dev -e app.main:app

test:
	. $(VENV)/bin/activate; $(PY) -m pytest

fmt:
	. $(VENV)/bin/activate; ruff format .

lint:
	. $(VENV)/bin/activate; ruff check .

type:
	. $(VENV)/bin/activate; mypy src

docker:
	docker build -t equipe3-api:local .

up:
	docker compose up --build

down:
	docker compose down

cov:
	. $(VENV)/bin/activate; $(PY) -m pytest --cov=src --cov-report=term-missing
