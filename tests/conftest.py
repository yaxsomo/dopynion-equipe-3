# tests/conftest.py
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app

# ---- HTTP client ----


@pytest.fixture(scope="session")
def client() -> TestClient:
    return TestClient(app)


# ---- Minimal game stubs (enough for strategy functions) ----


class StockStub:
    def __init__(self, quantities: dict[str, int] | None = None):
        self.quantities = quantities or {}


class HandStub:
    def __init__(self, quantities: dict[str, int] | None = None):
        self.quantities = quantities or {}


class PlayerStub:
    def __init__(self, name: str = "P", score: int = 0, hand: HandStub | None = None):
        self.name = name
        self.score = score
        self.hand = hand


class GameStub:
    def __init__(self, stock: dict[str, int], players: list[PlayerStub]):
        self.stock = StockStub(stock)
        self.players = players


# Factory helpers


@pytest.fixture
def make_game():
    def _make(
        stock: dict[str, int] | None = None,
        scores: list[int] = [0, 0],
    ) -> GameStub:
        stock = stock or {}
        players = [PlayerStub(name=f"P{i}", score=s) for i, s in enumerate(scores)]
        return GameStub(stock, players)

    return _make


@pytest.fixture
def simple_state():
    # Mirrors TURN_STATE entry shape
    return {
        "counts": {
            "gold": 0,
            "laboratory": 0,
            "market": 0,
            "festival": 0,
            "village": 0,
            "smithy": 0,
        },
        "actions_left": 1,
        "action_coins": 0,
        "extra_buys": 0,
        "buys_left": 1,
        "turn": 1,
        "gardens_plan": False,
        "phase": "ACTION",
    }
