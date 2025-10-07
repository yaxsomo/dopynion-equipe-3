#!/usr/bin/env bash
set -euo pipefail

# -------------------------------------------
# Bootstrap complet d'un dépôt pro FastAPI
# Crée l'arborescence, déplace les fichiers,
# installe la stack CI/CD, Docker, tests, etc.
# -------------------------------------------

echo "🚀 Bootstrapping repo..."

# 1) Arborescence
mkdir -p .github/workflows \
         src/app/routers \
         src/app/domain \
         src/app/models \
         tests/unit \
         tests/integration \
         api/openapi \
         scripts \
         .vscode

# 2) Déplacement fichiers existants
if [ -f "openapi.json" ]; then
  mv -f openapi.json api/openapi/openapi.json
elif [ -f "api/openapi.json" ]; then
  mv -f api/openapi.json api/openapi/openapi.json
fi

if [ -f "template.py" ]; then
  mv -f template.py src/app/legacy_template.py
elif [ -f "templates/template.py" ]; then
  mv -f templates/template.py src/app/legacy_template.py
fi

# 3) .gitignore
cat > .gitignore <<'EOF'
__pycache__/
*.pyc
*.pyo
*.pyd
.venv/
.env
.pytest_cache/
.mypy_cache/
htmlcov/
dist/
build/
.vscode/
.idea/
*.log
docker-data/
EOF

# 4) .editorconfig
cat > .editorconfig <<'EOF'
root = true

[*]
charset = utf-8
end_of_line = lf
insert_final_newline = true
indent_style = space
indent_size = 2

[*.py]
indent_size = 4
EOF

# 5) pyproject.toml
cat > pyproject.toml <<'EOF'
[build-system]
requires = ["setuptools>=68", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "dopynion-equipe-3"
version = "0.1.0"
description = "API de jeu (projet école) - FastAPI"
readme = "README.md"
requires-python = ">=3.10"
authors = [{ name = "Equipe 3" }]
dependencies = [
  "fastapi>=0.115",
  "uvicorn[standard]>=0.30",
  "pydantic>=2.6",
  "python-dotenv>=1.0",
]

[project.optional-dependencies]
dev = [
  "pytest>=8.2",
  "pytest-cov>=5.0",
  "httpx>=0.27",
  "ruff>=0.6.9",
  "mypy>=1.11",
  "types-requests",
  "pre-commit>=3.8",
]

[tool.ruff]
line-length = 100
target-version = "py310"
fix = true
select = ["E","F","I","B","UP","PL","RUF"]
ignore = ["E203","E501"]

[tool.ruff.format]
quote-style = "double"

[tool.mypy]
python_version = "3.10"
strict = true
ignore_missing_imports = true

[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-q --cov=src --cov-report=term-missing"
EOF

# 6) Pre-commit config
cat > .pre-commit-config.yaml <<'EOF'
repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.6.9
    hooks:
      - id: ruff
        args: ["--fix"]
      - id: ruff-format

  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v4.6.0
    hooks:
      - id: check-merge-conflict
      - id: check-yaml
      - id: end-of-file-fixer
      - id: trailing-whitespace
EOF

# 7) Docker
cat > Dockerfile <<'EOF'
FROM python:3.12-slim

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update && apt-get install -y --no-install-recommends \
      curl ca-certificates && \
    rm -rf /var/lib/apt/lists/*

COPY pyproject.toml ./
RUN python -m pip install --upgrade pip && \
    pip install .[dev]

COPY src ./src
COPY .env ./.env || true

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
EOF

cat > .dockerignore <<'EOF'
.git
.gitignore
.vscode
__pycache__
*.pyc
tests
htmlcov
.coverage
.env*
EOF

cat > docker-compose.yml <<'EOF'
services:
  api:
    build: .
    ports:
      - "8000:8000"
    env_file:
      - .env
    volumes:
      - ./src:/app/src:ro
EOF

# 8) Makefile
cat > Makefile <<'EOF'
.PHONY: setup precommit run test fmt lint type docker up down

setup:
	python -m pip install --upgrade pip
	pip install .[dev]
	pre-commit install

precommit:
	pre-commit run --all-files

run:
	uvicorn app.main:app --reload --port 8000

test:
	pytest

fmt:
	ruff format .

lint:
	ruff check .

type:
	mypy src

docker:
	docker build -t equipe3-api:local .

up:
	docker compose up --build

down:
	docker compose down
EOF

# 9) VSCode recommandations
cat > .vscode/extensions.json <<'EOF'
{
  "recommendations": [
    "ms-python.python",
    "ms-python.vscode-pylance",
    "charliermarsh.ruff"
  ]
}
EOF

# 10) .env example
cat > .env.example <<'EOF'
# Variables d'environnement pour l'API
APP_NAME="Equipe3 API"
APP_ENV="dev"
APP_DEBUG="true"
EOF
[ -f .env ] || cp .env.example .env

# 11) Squelette FastAPI
cat > src/app/main.py <<'EOF'
from fastapi import FastAPI
from .routers import game

app = FastAPI(title="Equipe 3 API", version="0.1.0")

@app.get("/health", tags=["meta"])
def health():
    return {"status": "ok"}

app.include_router(game.router, prefix="/game", tags=["game"])
EOF

cat > src/app/routers/game.py <<'EOF'
from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter()

class PlayRequest(BaseModel):
  player_id: str
  action: str

class PlayResponse(BaseModel):
  valid: bool
  message: str

@router.post("/play", response_model=PlayResponse)
def play(req: PlayRequest):
  if req.action not in {"buy", "trash", "end", "play"}:
    return PlayResponse(valid=False, message="Action invalide")
  return PlayResponse(valid=True, message=f"Action {req.action} acceptée")
EOF

# 12) Tests
cat > tests/unit/test_health.py <<'EOF'
from httpx import AsyncClient
import pytest
from app.main import app

@pytest.mark.asyncio
async def test_health():
    async with AsyncClient(app=app, base_url="http://test") as ac:
        r = await ac.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"
EOF

cat > tests/integration/test_play.py <<'EOF'
from httpx import AsyncClient
import pytest
from app.main import app

@pytest.mark.asyncio
async def test_play_invalid_action():
    async with AsyncClient(app=app, base_url="http://test") as ac:
        r = await ac.post("/game/play", json={"player_id": "p1", "action": "explode"})
    assert r.status_code == 200
    assert r.json()["valid"] is False
EOF

# 13) GitHub Actions
mkdir -p .github/workflows
cat > .github/workflows/ci.yml <<'EOF'
name: CI

on:
  push:
    branches: [ "**" ]
  pull_request:

jobs:
  tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - name: Install
        run: |
          python -m pip install --upgrade pip
          pip install .[dev]
      - name: Lint
        run: |
          ruff check .
          ruff format --check .
          mypy src
      - name: Tests
        run: pytest
EOF

# 14) README minimal
cat > README.md <<'EOF'
# Equipe 3 — API FastAPI

## 🚀 Démarrage rapide

```bash
make setup
make run
```

L’API sera dispo sur http://localhost:8000/docs

## 📦 Tests

```bash
make test
```

## 🐍 Linter / Type check

```bash
make lint
make fmt
make type
```

## 🐳 Docker

```bash
make up
```
EOF

# 15) Scripts helpers
mkdir -p scripts
cat > scripts/dev.sh <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
make setup
make run
EOF
chmod +x scripts/dev.sh

cat > scripts/test.sh <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
make precommit
make test
EOF
chmod +x scripts/test.sh

cat > scripts/run.sh <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
uvicorn app.main:app --reload --port 8000
EOF
chmod +x scripts/run.sh

# 16) LICENSE MIT si absent
if [ ! -f LICENSE ]; then
cat > LICENSE <<'EOF'
MIT License

Copyright (c) 2025 Equipe 3

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
EOF
fi

# 17) Init git si nécessaire
if [ ! -d .git ]; then
  git init -q
  git add .
  git commit -m "chore: bootstrap repo (api, ci, tests, docker, tooling)"
fi

echo "✅ Bootstrap terminé !"
echo "➡️ Prochaine étape :"
echo "   make setup && make run"
