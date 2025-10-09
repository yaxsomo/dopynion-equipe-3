# src/app/main.py
from __future__ import annotations

from fastapi import FastAPI
from fastapi.responses import HTMLResponse

from .routers import game

app = FastAPI(title="Equipe 3 API", version="0.1.0")

# --- Runtime-configurable default strategy for new games ---
# This is used ONLY when a client doesn't send the X-Strategy header.
DEFAULT_STRATEGY = "baseline"


@app.get("/", tags=["meta"], response_class=HTMLResponse)
def root() -> str:
    return "<html><body><h1>Equipe 3 API</h1><p>Docs: /docs</p><p>Health: /health</p></body></html>"


@app.get("/health", tags=["meta"])
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/strategy", tags=["config"])
def get_strategy() -> dict[str, str]:
    """Inspect the default strategy currently used for new games."""
    return {"default_strategy": DEFAULT_STRATEGY}


@app.post("/strategy/{strategy_name}", tags=["config"])
def change_strategy(strategy_name: str) -> dict[str, str]:
    """
    Change the default strategy for NEW games.
    Existing games keep whatever was stored in their state at /start_game time.
    """
    global DEFAULT_STRATEGY
    DEFAULT_STRATEGY = strategy_name.strip().lower()
    return {"message": f"default strategy set to '{DEFAULT_STRATEGY}'"}


@app.middleware("http")
async def inject_default_strategy(request, call_next):
    """
    If the client doesn't send X-Strategy, inject the current DEFAULT_STRATEGY
    so /start_game can persist it into the per-game state.
    """
    # Starlette headers are a list[tuple[bytes, bytes]] in request.scope["headers"]
    scope_headers = dict(request.scope.get("headers", []))
    if b"x-strategy" not in scope_headers:
        headers = list(request.scope.get("headers", []))
        headers.append((b"x-strategy", DEFAULT_STRATEGY.encode()))
        request.scope["headers"] = headers

    response = await call_next(request)
    return response


# Legacy / game routes
app.include_router(game.router, tags=["legacy"])
