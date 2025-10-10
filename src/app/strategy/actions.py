from __future__ import annotations

from dopynion.data_model import Game

from .constants import (
    ACTION_BUY_BONUS,
    ACTION_COIN_BONUS,
    ACTION_PLUS_ACTIONS,
    COSTS,
    MIN_COPPER_TRASH,
)
from .utils import safe_get_me


def _act_trashing(q: dict[str, int], actions_left: int, state: dict[str, object]) -> str | None:
    has_junk = (
        q.get("curse", 0) > 0 or q.get("estate", 0) > 0 or q.get("copper", 0) >= MIN_COPPER_TRASH
    )
    if q.get("chapel", 0) > 0 and has_junk:
        state["actions_left"] = actions_left - 1 + ACTION_PLUS_ACTIONS.get("chapel", 0)
        return "ACTION chapel"
    if q.get("moneylender", 0) > 0 and q.get("copper", 0) > 0:
        state["actions_left"] = actions_left - 1
        bonus = ACTION_COIN_BONUS.get("moneylender", 0)
        state["action_coins"] = int(state.get("action_coins", 0)) + bonus
        return "ACTION moneylender"
    if q.get("remodel", 0) > 0 or q.get("remake", 0) > 0:
        use = "remake" if q.get("remake", 0) > 0 else "remodel"
        state["actions_left"] = actions_left - 1
        return f"ACTION {use}"
    return None


def _act_nonterminal(q: dict[str, int], actions_left: int, state: dict[str, object]) -> str | None:
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
        if q.get(c, 0) > 0:
            state["actions_left"] = actions_left - 1 + ACTION_PLUS_ACTIONS.get(c, 0)
            coin_bonus = ACTION_COIN_BONUS.get(c, 0)
            buy_bonus = ACTION_BUY_BONUS.get(c, 0)
            state["action_coins"] = int(state.get("action_coins", 0)) + coin_bonus
            state["extra_buys"] = int(state.get("extra_buys", 0)) + buy_bonus
            return f"ACTION {c}"
    return None


def _act_attacks(q: dict[str, int], actions_left: int, state: dict[str, object]) -> str | None:
    for c in ("witch", "militia", "bandit", "bureaucrat"):
        if q.get(c, 0) > 0:
            state["actions_left"] = actions_left - 1
            return f"ACTION {c}"
    return None


def _act_terminal_draw(
    q: dict[str, int], actions_left: int, state: dict[str, object]
) -> str | None:
    for c in ("councilroom", "smithy", "library", "adventurer"):
        if q.get(c, 0) > 0:
            state["actions_left"] = actions_left - 1
            coin_bonus = ACTION_COIN_BONUS.get(c, 0)
            buy_bonus = ACTION_BUY_BONUS.get(c, 0)
            state["action_coins"] = int(state.get("action_coins", 0)) + coin_bonus
            state["extra_buys"] = int(state.get("extra_buys", 0)) + buy_bonus
            return f"ACTION {c}"
    return None


def _act_economy(q: dict[str, int], actions_left: int, state: dict[str, object]) -> str | None:
    for c in ("mine", "feast", "workshop"):
        if q.get(c, 0) > 0:
            state["actions_left"] = actions_left - 1
            return f"ACTION {c}"
    return None


def choose_action(game: Game, me_idx: int, state: dict[str, object]) -> str | None:
    """Decide which ACTION to play this call, if any."""
    me = safe_get_me(game, me_idx)
    if not me or not getattr(me, "hand", None):
        return None

    q = (me.hand.quantities or {}) or {}

    actions_left = int(state.get("actions_left", 1))
    if actions_left <= 0:
        return None

    actionable = [
        k
        for k in q
        if k in COSTS and k not in {"copper", "silver", "gold", "estate", "duchy", "province"}
    ]
    if not actionable:
        return None

    # Try sub-pickers in order
    for picker in (_act_trashing, _act_nonterminal, _act_attacks, _act_terminal_draw, _act_economy):
        decision = picker(q, actions_left, state)
        if decision is not None:
            return decision

    return None
