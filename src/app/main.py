# src/app/main.py
from __future__ import annotations

from fastapi import FastAPI

from .routers import (
    game,
    legacy,  # <- nouveau router
)

app = FastAPI(title="Equipe 3 API", version="0.1.0")


@app.get("/", tags=["meta"])
def root() -> dict[str, str]:
    return {"name": "Equipe 3 API", "docs": "/docs", "health": "/health"}


@app.get("/health", tags=["meta"])
def health() -> dict[str, str]:
    return {"status": "ok"}


# routes internes existantes
app.include_router(game.router, prefix="/game", tags=["game"])
# routes legacy “dopynion”
app.include_router(legacy.router, tags=["legacy"])
