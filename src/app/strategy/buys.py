from __future__ import annotations

from dopynion.data_model import Game

from .constants import (
    BEHIND_DUCHY_DEFICIT,
    BUY_4_COST_COINS,
    BUY_5_COST_COINS,
    BUY_GOLD_COINS,
    BUY_PROVINCE_COINS,
    BUY_SILVER_COINS,
    COINS_EQ_3,
    COINS_EQ_4,
    COINS_EQ_5,
    EARLY_HIRELING_TURN,
    EARLY_PROVINCE_STOCK,
    ENDGAME_PROVINCE_THRESHOLD,
    ENGINE_GOLD_THRESHOLD,
    ENGINE_LAB_THRESHOLD,
    ENGINE_MF_SUM_THRESHOLD,
    FIVE_COST_PREFER,
    MAX_LABS,
    MIDGAME_PROVINCE_THRESHOLD,
    MIN_GREEN_TURN,
    OPENING_TURN_LIMIT,
    PROVINCE_SOFT_CAP_BEFORE_TURN,
    PROVINCES_ALLOWED_BEFORE_CAP,
    RUSH_TURN,
)
from .utils import in_stock, terminal_capacity

# ---- engine readiness & early green ----


def engine_ready(counts: dict[str, int]) -> bool:
    if counts.get("gold", 0) >= ENGINE_GOLD_THRESHOLD:
        return True
    if counts.get("laboratory", 0) >= ENGINE_LAB_THRESHOLD:
        return True
    if counts.get("market", 0) + counts.get("festival", 0) >= ENGINE_MF_SUM_THRESHOLD:
        return True
    if (
        counts.get("village", 0) >= 1
        and (counts.get("smithy", 0) + counts.get("councilroom", 0) + counts.get("library", 0)) >= 1
    ):
        return True
    return False


def early_province_ok(
    counts: dict[str, int],
    provinces_left: int,
    turn: int,
    score_gap: int,
) -> bool:
    if turn >= RUSH_TURN:
        return True
    if provinces_left <= EARLY_PROVINCE_STOCK:
        return True
    if engine_ready(counts):
        return True
    if turn < MIN_GREEN_TURN and score_gap > -BEHIND_DUCHY_DEFICIT:
        return False

    my_provinces = counts.get("province", 0)
    if turn < PROVINCE_SOFT_CAP_BEFORE_TURN and my_provinces >= PROVINCES_ALLOWED_BEFORE_CAP:
        return False
    if score_gap <= -BEHIND_DUCHY_DEFICIT:
        return True
    if turn >= MIN_GREEN_TURN:
        return True
    return False


# ---- mid/end game VP pressure ----


def endgame_buy(
    game: Game, coins: int, provinces_left: int, my_score: int, best_opp: int, turn: int
) -> str | None:
    if turn >= RUSH_TURN:
        if coins >= BUY_PROVINCE_COINS and game.stock.quantities.get("province", 0) > 0:
            return "BUY province"
        if coins >= BUY_5_COST_COINS and in_stock(game, "duchy"):
            return "BUY duchy"
        if coins >= BUY_SILVER_COINS and in_stock(game, "estate"):
            return "BUY estate"
        return None

    if provinces_left <= ENDGAME_PROVINCE_THRESHOLD:
        if coins >= BUY_PROVINCE_COINS and game.stock.quantities.get("province", 0) > 0:
            return "BUY province"
        if coins >= BUY_5_COST_COINS and in_stock(game, "duchy"):
            return "BUY duchy"
        if coins >= BUY_SILVER_COINS and in_stock(game, "estate"):
            return "BUY estate"
    return None


def midgame_buy(
    game: Game, coins: int, provinces_left: int, my_score: int, best_opp: int, turn: int
) -> str | None:
    if turn >= RUSH_TURN and coins >= BUY_PROVINCE_COINS and in_stock(game, "province"):
        return "BUY province"
    if provinces_left <= MIDGAME_PROVINCE_THRESHOLD:
        if coins >= BUY_PROVINCE_COINS and in_stock(game, "province"):
            return "BUY province"
        if coins >= BUY_5_COST_COINS and in_stock(game, "duchy") and my_score <= best_opp:
            return "BUY duchy"
    if (best_opp - my_score) >= BEHIND_DUCHY_DEFICIT and coins >= BUY_5_COST_COINS:
        if in_stock(game, "duchy"):
            return "BUY duchy"
    return None


# ---- value buys by price point ----


def economy_buy(game: Game, coins: int) -> str | None:
    if coins >= BUY_GOLD_COINS and game.stock.quantities.get("gold", 0) > 0:
        return "BUY gold"
    return None


def five_wishlist(game: Game, counts: dict[str, int], coins: int, gardens_plan: bool) -> list[str]:
    picks: list[str] = []
    has_curses = game.stock.quantities.get("curse", 0) > 0
    if has_curses and in_stock(game, "witch"):
        picks.append("witch")

    if in_stock(game, "laboratory") and counts.get("laboratory", 0) < MAX_LABS:
        picks.append("laboratory")

    if terminal_capacity(counts) <= 0:
        for c in ("market", "festival"):
            if in_stock(game, c):
                picks.append(c)
        if in_stock(game, "village") and coins >= BUY_4_COST_COINS:
            picks.append("village")

    if gardens_plan:
        for c in ("market", "festival", "laboratory"):
            if in_stock(game, c):
                picks.append(c)

    for c in FIVE_COST_PREFER:
        if in_stock(game, c):
            picks.append(c)

    if in_stock(game, "silver"):
        picks.append("silver")

    return picks


def five_cost_buy(game: Game, coins: int, counts: dict[str, int], gardens_plan: bool) -> str | None:
    if coins < BUY_5_COST_COINS:
        return None
    w = five_wishlist(game, counts, coins, gardens_plan)
    return f"BUY {w[0]}" if w else None


def four_cost_buy(game: Game, coins: int, counts: dict[str, int]) -> str | None:
    if coins < BUY_4_COST_COINS:
        return None
    for c in ("moneylender", "militia", "port", "poacher", "remodel", "remake"):
        if in_stock(game, c):
            return f"BUY {c}"
    if terminal_capacity(counts) <= 0 and in_stock(game, "village"):
        return "BUY village"
    if in_stock(game, "smithy"):
        return "BUY smithy"
    if in_stock(game, "gardens"):
        return "BUY gardens"
    if in_stock(game, "silver"):
        return "BUY silver"
    return None


def three_cost_buy(game: Game, coins: int) -> str | None:
    if coins < COINS_EQ_3:
        return None
    for c in ("workshop", "village", "woodcutter"):
        if in_stock(game, c):
            return f"BUY {c}"
    if in_stock(game, "silver"):
        return "BUY silver"
    return None


# ---- openings ----


def opening_buy_5plus(game: Game) -> str | None:
    if game.stock.quantities.get("curse", 0) > 0 and in_stock(game, "witch"):
        return "BUY witch"
    for c in ("laboratory", "market", "festival", "councilroom"):
        if in_stock(game, c):
            return f"BUY {c}"
    return None


def opening_buy_4(game: Game) -> str | None:
    for c in ("moneylender", "militia", "smithy", "remodel", "remake", "poacher", "port"):
        if in_stock(game, c):
            return f"BUY {c}"
    if in_stock(game, "village"):
        return "BUY village"
    if in_stock(game, "silver"):
        return "BUY silver"
    return None


def opening_buy_3(game: Game) -> str | None:
    for c in ("workshop", "village", "woodcutter"):
        if in_stock(game, c):
            return f"BUY {c}"
    if in_stock(game, "silver"):
        return "BUY silver"
    return None


def opening_buy_2(game: Game, counts: dict[str, int]) -> str | None:
    if counts.get("chapel", 0) == 0 and in_stock(game, "chapel"):
        return "BUY chapel"
    if in_stock(game, "cellar"):
        return "BUY cellar"
    if in_stock(game, "estate"):
        return "BUY estate"
    return None


def opening_buys(game: Game, coins: int, counts: dict[str, int], turn: int) -> str | None:
    if turn > OPENING_TURN_LIMIT:
        return None
    if coins >= COINS_EQ_5:
        pick = opening_buy_5plus(game)
        if pick:
            return pick
    if coins == COINS_EQ_4:
        pick = opening_buy_4(game)
        if pick:
            return pick
    if coins == COINS_EQ_3:
        pick = opening_buy_3(game)
        if pick:
            return pick
    if coins == BUY_4_COST_COINS - 2:
        return opening_buy_2(game, counts)
    return None


# ---- special 6-cost logic (safer) ----


def six_cost_buy(game: Game, coins: int, counts: dict[str, int], turn: int) -> str | None:
    if coins < BUY_GOLD_COINS:
        return None
    if (
        in_stock(game, "hireling")
        and counts.get("hireling", 0) == 0
        and turn <= EARLY_HIRELING_TURN
    ):
        return "BUY hireling"

    if (
        in_stock(game, "distantshore")
        and engine_ready(counts)
        and turn < (RUSH_TURN - EARLY_HIRELING_TURN)
    ):
        return "BUY distantshore"
    return None
