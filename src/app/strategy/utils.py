from __future__ import annotations

# Unified utility exports for strategies/pipeline/actions.
# This file is defensive about different Game/Player shapes so imports never fail.

from typing import Any, Iterable, Optional, Tuple, Dict


# ---------------------------------------------------------------------------
# Stock helpers
# ---------------------------------------------------------------------------

def _extract_stock(obj: Any) -> dict:
    """
    Try to obtain a {card_name: qty} mapping from different shapes:
    - Game-like: game.stock.quantities (dict)
    - state dict: state["game"].stock.quantities
    - dict that already looks like quantities (mapping card -> qty)
    """
    try:
        stock = getattr(getattr(obj, "stock", None), "quantities", None)
        if isinstance(stock, dict):
            return stock
        if isinstance(obj, dict):
            game = obj.get("game")
            if game is not None:
                stock = getattr(getattr(game, "stock", None), "quantities", None)
                if isinstance(stock, dict):
                    return stock
            maybe = obj.get("stock", obj)
            if isinstance(maybe, dict):
                return maybe
    except Exception:
        pass
    return {}


def in_stock(game_or_state: Any, card: str) -> bool:
    """True if the supply pile for `card` has > 0 copies remaining."""
    stock = _extract_stock(game_or_state)
    return int(stock.get(card.lower(), 0)) > 0


# Backward-/side-compat shim some callers use
def in_stock_state(game_or_state: Any, card: str) -> bool:  # alias
    return in_stock(game_or_state, card)


def best_from(game_or_state: Any, candidates: Iterable[str]) -> Optional[str]:
    """
    Return the first card in `candidates` that is currently in stock, else None.
    (Just a tiny helper to avoid boilerplate in strategies.)
    """
    for c in candidates:
        if in_stock(game_or_state, c):
            return c
    return None


# ---------------------------------------------------------------------------
# Player helpers
# ---------------------------------------------------------------------------

def _get_attr_or_key(obj: Any, *names: str):
    """Return the first attribute/key found among names, else None."""
    for n in names:
        if hasattr(obj, n):
            return getattr(obj, n)
    if isinstance(obj, dict):
        for n in names:
            if n in obj:
                return obj[n]
    return None


def safe_get_me(game: Any, me_idx: Any) -> Optional[Any]:
    """
    Best-effort retrieval of 'my' player object from a Game or game-like dict.
    Tries (in order):
    - game.me (if it's already a player object)
    - game.me as an index into game.players / players_info / playersInfos
    - me_idx (provided by the server) into the same players list
    - a player with 'is_me' / 'me' flag
    Returns the player object or None if not found.
    """
    if game is None:
        return None

    me_field = _get_attr_or_key(game, "me")
    if me_field is not None and not isinstance(me_field, (int, float)):
        return me_field  # already a player object

    players = _get_attr_or_key(game, "players", "players_info", "playersInfos")
    if isinstance(players, (list, tuple)):
        # game.me is an index?
        if isinstance(me_field, (int, float)):
            mi = int(me_field)
            if 0 <= mi < len(players):
                return players[mi]
        # me_idx provided?
        try:
            idx = int(me_idx)
            if 0 <= idx < len(players):
                return players[idx]
        except Exception:
            pass
        # Flag-based fallback
        for p in players:
            if getattr(p, "is_me", False) or getattr(p, "me", False):
                return p
    return None


# ---------------------------------------------------------------------------
# Scoring / capacity
# ---------------------------------------------------------------------------

def _player_score(p: Any) -> int:
    """
    Best-effort extraction of a player's score. Tries common attribute names.
    Falls back to 0 if unknown.
    """
    for name in ("score", "victory_points", "victoryPoints", "vp", "points"):
        try:
            v = getattr(p, name, None)
            if v is None and isinstance(p, dict):
                v = p.get(name)
            if v is not None:
                return int(v)
        except Exception:
            continue
    # If you later want to compute VP from piles, wire it here.
    return 0


def score_status(game: Any, me_idx: Any) -> Tuple[int, int]:
    """
    Returns (my_score, best_opponent_score). Robust to different Game shapes.
    """
    me = safe_get_me(game, me_idx)
    my_score = _player_score(me) if me is not None else 0

    # Get players list
    players = _get_attr_or_key(game, "players", "players_info", "playersInfos")
    best_opp = 0
    if isinstance(players, (list, tuple)):
        for p in players:
            if p is me:
                continue
            best_opp = max(best_opp, _player_score(p))
    return my_score, best_opp


def terminal_capacity(counts: Dict[str, int]) -> int:
    """
    Heuristic 'action capacity' of the deck:
    +Actions producers (approx) minus number of terminal action cards.
    Positive => you can add more terminals safely.
    """
    c = {k: int(v) for k, v in (counts or {}).items()}

    # +Actions producers (common base/near-base cards)
    plus_actions = (
        2 * c.get("village", 0) +
        1 * c.get("market", 0) +
        1 * c.get("laboratory", 0) +
        2 * c.get("festival", 0) +
        2 * c.get("port", 0) +
        1 * c.get("poacher", 0) +
        1 * c.get("cellar", 0) +
        2 * c.get("farmingvillage", 0) +
        1 * c.get("magpie", 0)
    )

    # Terminals we commonly buy
    terminals = (
        c.get("smithy", 0) +
        c.get("witch", 0) +
        c.get("militia", 0) +
        c.get("bandit", 0) +
        c.get("bureaucrat", 0) +
        c.get("chancellor", 0) +
        c.get("woodcutter", 0) +
        c.get("moneylender", 0) +
        c.get("remodel", 0) +
        c.get("remake", 0) +
        c.get("mine", 0) +
        c.get("feast", 0) +
        c.get("workshop", 0)
    )

    return plus_actions - terminals


# ---------------------------------------------------------------------------
# Module export list (safe even if __all__ didn't exist before)
# ---------------------------------------------------------------------------

try:
    __all__  # type: ignore
except NameError:
    __all__ = []

for _name in [
    "in_stock", "in_stock_state", "best_from",
    "safe_get_me", "score_status", "terminal_capacity",
]:
    if _name not in __all__:
        __all__.append(_name)
