# src/app/main.py
from fastapi import FastAPI

from .routers import game

app = FastAPI(title="Equipe 3 API", version="0.1.0")


@app.get("/", tags=["meta"])
def root():
    return {"name": "Equipe 3 API", "docs": "/docs", "health": "/health"}


@app.get("/health", tags=["meta"])
def health():
    return {"status": "ok"}


app.include_router(game.router, prefix="/game", tags=["game"])
