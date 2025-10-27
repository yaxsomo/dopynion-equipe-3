from __future__ import annotations

from collections import defaultdict
from typing import Dict

# Per-game, in-memory turn state.
# Keys are X-Game-Id; values are dicts mutated across a single match.
TURN_STATE: Dict[str, Dict[str, object]] = defaultdict(
    lambda: {
        "turn": 1,
        "phase": "ACTION",          # optional, used by some logs
        "bought": False,
        "counts": defaultdict(int), # card -> count we've bought

        # Buy-phase bookkeeping (re-initialized at start of each turn)
        "action_coins": 0,
        "extra_buys": 0,
        "coins_left": 0,
        "buys_left": 1,
        "initialized_resources": False,
    }
)

def get(game_id: str) -> Dict[str, object]:
    """Return the mutable state dict for a given game id; create if missing."""
    return TURN_STATE[game_id]

# Back-compat alias (some modules use get_state instead of get)
def get_state(game_id: str) -> Dict[str, object]:
    return get(game_id)

def reset_for_new_turn(game_id: str) -> None:
    """Reset per-turn counters at the start of a new turn."""
    st = TURN_STATE[game_id]
    st["phase"] = "ACTION"
    st["bought"] = False
    st["action_coins"] = 0
    st["extra_buys"] = 0
    st["coins_left"] = 0
    st["buys_left"] = 1
    st["initialized_resources"] = False

__all__ = ["TURN_STATE", "get", "get_state", "reset_for_new_turn"]
