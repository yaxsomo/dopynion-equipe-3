# --- Compatibility shim: in_stock_state --------------------------------------
from typing import Any

def in_stock_state(state_or_game: Any, card: str) -> bool:
    """
    Return True if the supply pile for `card` has > 0 copies remaining.
    Accepts:
      - a Game (with .stock.quantities),
      - a state dict with a 'game' entry,
      - a dict that itself looks like stock/quantities (mapping card -> qty).
    """
    try:
        # Case 1: Game-like
        stock = getattr(getattr(state_or_game, "stock", None), "quantities", None)
        if isinstance(stock, dict):
            return (stock or {}).get(card, 0) > 0

        # Case 2: state dict -> game -> stock
        if isinstance(state_or_game, dict):
            game = state_or_game.get("game")
            if game is not None:
                stock = getattr(getattr(game, "stock", None), "quantities", None)
                if isinstance(stock, dict):
                    return (stock or {}).get(card, 0) > 0

            # Case 3: raw quantities-like dict
            maybe_qty = state_or_game.get("stock", state_or_game)
            if isinstance(maybe_qty, dict):
                return (maybe_qty or {}).get(card, 0) > 0

    except Exception:
        pass

    return False

try:
    __all__.append("in_stock_state")  # if you use __all__
except Exception:
    pass
