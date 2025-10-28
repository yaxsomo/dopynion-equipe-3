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
# --- Coin computation helpers -------------------------------------------------
from typing import Any, Dict, Iterable

# Base Dominion treasure values (extend if you use expansions)
_TREASURE_VALUES: Dict[str, int] = {
    "copper": 1,
    "silver": 2,
    "gold": 3,
    # Uncomment/extend if applicable:
    # "platinum": 5,
}

def _to_quantities_from_hand(hand_obj: Any) -> Dict[str, int]:
    """
    Normalize a player's hand into {card_name_lower: count}.
    Supports:
      - hand.quantities (dict-like)
      - hand as a list/tuple of card names
      - hand as a dict {card_name: count}
    """
    # Case 1: object with .quantities
    qty = getattr(hand_obj, "quantities", None)
    if isinstance(qty, dict):
        return {str(k).lower(): int(v) for k, v in qty.items()}

    # Case 2: iterable of names
    if isinstance(hand_obj, (list, tuple)):
        out: Dict[str, int] = {}
        for x in hand_obj:
            k = str(x).lower()
            out[k] = out.get(k, 0) + 1
        return out

    # Case 3: already a dict
    if isinstance(hand_obj, dict):
        return {str(k).lower(): int(v) for k, v in hand_obj.items()}

    return {}

def _extract_player_hand(game_or_state: Any, me_idx: Any) -> Any:
    """Return a 'hand' object from a Game-like or state dict."""
    # Prefer a direct 'me' object with .hand
    me = safe_get_me(game_or_state, me_idx)
    if me is not None:
        h = getattr(me, "hand", None) or (me.get("hand") if isinstance(me, dict) else None)
        if h is not None:
            return h

    # Try game.me.hand if me_idx lookup failed
    try:
        me_obj = getattr(game_or_state, "me", None)
        if me_obj is not None:
            h = getattr(me_obj, "hand", None)
            if h is not None:
                return h
    except Exception:
        pass

    # Try state dict path: state["game"]["players"][me_idx]["hand"]
    if isinstance(game_or_state, dict):
        g = game_or_state.get("game")
        if g is not None:
            try:
                players = getattr(g, "players", None) or getattr(g, "players_info", None) or getattr(g, "playersInfos", None)
                if players and 0 <= int(me_idx) < len(players):
                    h = getattr(players[int(me_idx)], "hand", None)
                    if h is not None:
                        return h
            except Exception:
                pass

    return None

def compute_treasure_coins(game_or_state: Any, me_idx: Any) -> int:
    """
    Sum coin value of treasures currently in hand (Copper/Silver/Gold...).
    Does NOT include +$ from actions; see compute_total_coins for that.
    """
    hand = _extract_player_hand(game_or_state, me_idx)
    q = _to_quantities_from_hand(hand) if hand is not None else {}
    total = 0
    for name, cnt in q.items():
        total += _TREASURE_VALUES.get(name, 0) * int(cnt)
    return total

def compute_total_coins(game_or_state: Any, me_idx: Any, state: Any = None) -> int:
    """
    Treasures in hand + action coins from state (if provided).
    Safe to call even if state is None or missing fields.
    """
    base = compute_treasure_coins(game_or_state, me_idx)
    bonus = 0
    if isinstance(state, dict):
        try:
            bonus = int(state.get("action_coins", 0))
        except Exception:
            bonus = 0
    return base + bonus

# Export
try:
    __all__.extend(["compute_treasure_coins", "compute_total_coins"])
except Exception:
    pass

