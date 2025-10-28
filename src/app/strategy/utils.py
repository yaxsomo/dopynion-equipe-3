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
