# --- Supply helpers -----------------------------------------------------------
from typing import Any

def _extract_stock(obj: Any) -> dict:
    """
    Try to obtain a {card_name: qty} mapping from different shapes:
    - Game -> .stock.quantities (dict)
    - dict with key 'stock' or already a {card: qty} dict
    - state dict that contains a Game under 'game'
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

# Backward-/side-compat shim: some callers import in_stock_state
def in_stock_state(game_or_state: Any, card: str) -> bool:
    return in_stock(game_or_state, card)

try:
    __all__.extend(["in_stock", "in_stock_state"])
except Exception:
    pass

    pass
# --- Player helpers -----------------------------------------------------------
from typing import Any, Optional

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
    - game.me as an index into game.players / game.players_info / game.playersInfos
    - me_idx (provided by the server) into the same players list
    - a player with a truthy 'is_me' / 'me' flag
    Returns the player object or None if not found.
    """
    if game is None:
        return None

    # Case 1: game.me is already a player object
    me_field = _get_attr_or_key(game, "me")
    if me_field is not None and not isinstance(me_field, (int, float)):
        return me_field

    # Normalize players list
    players = _get_attr_or_key(game, "players", "players_info", "playersInfos")
    if isinstance(players, (list, tuple)):
        # Case 2: game.me is an index
        if isinstance(me_field, (int, float)):
            mi = int(me_field)
            if 0 <= mi < len(players):
                return players[mi]

        # Case 3: me_idx is provided
        try:
            idx = int(me_idx)
            if 0 <= idx < len(players):
                return players[idx]
        except Exception:
            pass

        # Case 4: look for a flag on players
        for p in players:
            if getattr(p, "is_me", False) or getattr(p, "me", False):
                return p

    return None

# If you maintain __all__, export the helper
try:
    __all__.append("safe_get_me")
except Exception:
    pass
