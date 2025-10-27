from __future__ import annotations

from collections import defaultdict
from typing import NamedTuple

from .constants import TEAM_NAME

# Per-game mutable state, keyed by game_id
TURN_STATE: dict[str, dict[str, object]] = defaultdict(
    lambda: {"bought": False, "counts": defaultdict(int)}
)


class BuyCtx(NamedTuple):
    provinces_left: int
    score_gap: int
    turn: int


def get_state(game_id: str) -> dict[str, object]:
    """Return mutable per-game state dict with keys: bought, counts, etc."""
    state = TURN_STATE[game_id]
    if "counts" not in state or not isinstance(state["counts"], defaultdict):
        state["counts"] = defaultdict(int)
    return state


__all__ = ["TEAM_NAME", "TURN_STATE", "BuyCtx", "get_state"]
