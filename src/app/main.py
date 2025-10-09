# src/app/main.py
from __future__ import annotations

from fastapi import FastAPI
from fastapi.responses import HTMLResponse

from .routers import game

app = FastAPI(title="Equipe 3 API", version="0.1.0")


@app.get("/", tags=["meta"], response_class=HTMLResponse)
def root() -> str:
    return "<html><body><h1>Equipe 3 API</h1><p>Docs: /docs</p><p>Health: /health</p></body></html>"


@app.get("/health", tags=["meta"])
def health() -> dict[str, str]:
    return {"status": "ok"}


app.include_router(game.router, tags=["legacy"])
