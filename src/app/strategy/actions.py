from __future__ import annotations
from dopynion.data_model import Game
from .utils import safe_get_me

from .constants import (
    ACTION_BUY_BONUS,
    ACTION_COIN_BONUS,
    ACTION_PLUS_ACTIONS,
    COSTS,
    MIN_COPPER_TRASH,
)


def _act_trashing(q: dict[str, int], actions_left: int, state: dict[str, object]) -> str | None:
    """Play strong trashers first while we still have actions."""
    has_junk = (q.get("curse", 0) + q.get("estate", 0) + q.get("copper", 0)) > 0
    if actions_left <= 0 or not has_junk:
        return None

    # Chapel: best early trash (don’t play if no junk)
    if q.get("chapel", 0) and has_junk:
        state["actions_left"] = actions_left - 1 + ACTION_PLUS_ACTIONS.get("chapel", 0)
        return "ACTION chapel"

    # Moneylender: only if we have copper
    if q.get("moneylender", 0) and q.get("copper", 0):
        state["actions_left"] = actions_left - 1
        state["action_coins"] = int(state.get("action_coins", 0)) + ACTION_COIN_BONUS.get("moneylender", 0)
        return "ACTION moneylender"

    # Remodel/Remake if present
    for c in ("remake", "remodel"):
        if q.get(c, 0):
            state["actions_left"] = actions_left - 1
            return f"ACTION {c}"

    return None


def _act_nonterminal(q: dict[str, int], actions_left: int, state: dict[str, object]) -> str | None:
    """Safe non-terminals (draw/+actions/payload that replace themselves)."""
    order = (
        "village",
        "market",
        "laboratory",
        "festival",
        "distantshore",
        "port",
        "cellar",
        "farmingvillage",
        "magpie",
        "poacher",
    )
    for c in order:
        if q.get(c, 0):
            state["actions_left"] = actions_left - 1 + ACTION_PLUS_ACTIONS.get(c, 0)
            # add payload if any
            state["action_coins"] = int(state.get("action_coins", 0)) + ACTION_COIN_BONUS.get(c, 0)
            state["extra_buys"] = int(state.get("extra_buys", 0)) + ACTION_BUY_BONUS.get(c, 0)
            return f"ACTION {c}"
    return None


def _act_attacks(q: dict[str, int], actions_left: int, state: dict[str, object]) -> str | None:
    """Attacks: punish and/or gain payload."""
    for c in ("witch", "militia", "bandit", "bureaucrat"):
        if q.get(c, 0):
            state["actions_left"] = actions_left - 1
            return f"ACTION {c}"
    return None


def _act_terminal_draw(q: dict[str, int], actions_left: int, state: dict[str, object]) -> str | None:
    """Pure terminal drawers (no +action)."""
    for c in ("councilroom", "smithy", "library", "adventurer"):
        if q.get(c, 0):
            state["actions_left"] = actions_left - 1
            # apply any coin/buy payload the card might give (e.g., Council Room)
            state["action_coins"] = int(state.get("action_coins", 0)) + ACTION_COIN_BONUS.get(c, 0)
            state["extra_buys"] = int(state.get("extra_buys", 0)) + ACTION_BUY_BONUS.get(c, 0)
            return f"ACTION {c}"
    return None


def _act_payload_terminals(q: dict[str, int], actions_left: int, state: dict[str, object]) -> str | None:
    """
    Woodcutter / Chancellor (and similar): terminal +$ and/or +Buy.
    We previously skipped these; now we always play them when we have an action.
    """
    for c in ("woodcutter", "chancellor"):
        if q.get(c, 0):
            state["actions_left"] = actions_left - 1
            state["action_coins"] = int(state.get("action_coins", 0)) + ACTION_COIN_BONUS.get(c, 0)
            state["extra_buys"] = int(state.get("extra_buys", 0)) + ACTION_BUY_BONUS.get(c, 0)
            return f"ACTION {c}"
    return None


def _act_economy(q: dict[str, int], actions_left: int, state: dict[str, object]) -> str | None:
    """Gainers / upgraders if nothing else is better."""
    for c in ("mine", "feast", "workshop"):
        if q.get(c, 0):
            state["actions_left"] = actions_left - 1
            return f"ACTION {c}"
    return None


def choose_action(game: Game, me_idx: int, state: dict[str, object]) -> str | None:
    """Pick one action card to play (or None)."""
    me = safe_get_me(game, me_idx)
    if not me or not getattr(me, "hand", None):
        return None
    q = (me.hand.quantities or {}) or {}

    actions_left = int(state.get("actions_left", 1))
    if actions_left <= 0:
        return None

    # No actions in hand?
    actionable = [k for k in q if k in COSTS and k not in {"copper", "silver", "gold", "estate", "duchy", "province"}]
    if not actionable:
        return None

    # Try sub-pickers in order
    for picker in (_act_trashing, _act_nonterminal, _act_attacks, _act_terminal_draw, _act_payload_terminals, _act_economy):
        decision = picker(q, actions_left, state)
        if decision is not None:
            return decision

    return None
