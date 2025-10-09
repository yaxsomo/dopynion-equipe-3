from __future__ import annotations

from dopynion.data_model import Game

from .constants import BEHIND_DUCHY_DEFICIT
from .utils import in_stock, score_status


def should_pivot_to_gardens(game: Game, me_idx: int) -> bool:
    if not in_stock(game, "gardens"):
        return False
    provinces_left = game.stock.quantities.get("province", 0)
    if provinces_left < 10:
        return False
    my, opp = score_status(game, me_idx)
    gap = my - opp
    buys_exist = in_stock(game, "market") or in_stock(game, "festival")
    return gap <= -(BEHIND_DUCHY_DEFICIT + 4) and buys_exist
