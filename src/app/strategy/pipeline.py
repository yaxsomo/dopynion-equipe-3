from __future__ import annotations
from dopynion.data_model import Game
from .constants import BUY_GOLD_COINS

from .buys import (
    early_province_ok,
    economy_buy,
    endgame_buy,
    five_cost_buy,
    four_cost_buy,
    midgame_buy,
    opening_buys,
    six_cost_buy,
    three_cost_buy,
)
from .constants import (
    BUY_4_COST_COINS,
    BUY_PROVINCE_COINS,
    BUY_SILVER_COINS,
    RUSH_TURN,
)
from .state import BuyCtx
from .utils import in_stock, score_status, terminal_capacity


def step_opening(game: Game, coins: int, counts: dict[str, int], turn: int) -> str | None:
    return opening_buys(game, coins, counts, turn)


def step_province_if_ok(game: Game, coins: int, counts: dict[str, int], ctx: BuyCtx) -> str | None:
    if coins >= BUY_PROVINCE_COINS and in_stock(game, "province"):
        if early_province_ok(counts, ctx.provinces_left, ctx.turn, ctx.score_gap):
            return "BUY province"
    return None


def step_gold_if_building(
    game: Game, coins: int, counts: dict[str, int], ctx: BuyCtx
) -> str | None:
    # Buy Gold at 6 if we *aren't* in an early-province window.
    # This accelerates the deck into province range.

    if coins >= BUY_GOLD_COINS and in_stock(game, "gold"):
        if not early_province_ok(counts, ctx.provinces_left, ctx.turn, ctx.score_gap):
            return "BUY gold"
    return None


def step_vp_override(game: Game, coins: int, ctx: BuyCtx) -> str | None:
    """Be more aggressive about greening as piles/turns run low."""
    # If provinces are getting low OR we are close to rush, prioritize VP.
    if ctx.provinces_left <= 4 or ctx.turn >= (RUSH_TURN - 5):
        if coins >= 8 and in_stock(game, "province"):
            return "BUY province"
        if coins >= 5 and in_stock(game, "duchy"):
            return "BUY duchy"
        if coins >= 2 and in_stock(game, "estate"):
            return "BUY estate"
    return None


def step_endgame(game: Game, coins: int, ctx: BuyCtx, my_score: int, best_opp: int) -> str | None:
    return endgame_buy(game, coins, ctx.provinces_left, my_score, best_opp, ctx.turn)


def step_midgame(game: Game, coins: int, ctx: BuyCtx, my_score: int, best_opp: int) -> str | None:
    return midgame_buy(game, coins, ctx.provinces_left, my_score, best_opp, ctx.turn)


def step_gardens_primary(game: Game, coins: int, gardens_plan: bool) -> str | None:
    if gardens_plan and coins >= BUY_4_COST_COINS and in_stock(game, "gardens"):
        return "BUY gardens"
    return None


def step_gardens_secondary(
    game: Game, coins: int, counts: dict[str, int], gardens_plan: bool
) -> str | None:
    if not gardens_plan:
        return None
    return five_cost_buy(game, coins, counts, gardens_plan=True)


def step_silver_floor(game: Game, coins: int, counts: dict[str, int], turn: int) -> str | None:
    """Ensure baseline economy at 3 or 4 coins in the early/mid build."""
    if coins in (3, 4) and counts.get("silver", 0) < 2 and turn <= 10:
        if in_stock(game, "silver"):
            return "BUY silver"
    return None


def step_economy(game: Game, coins: int) -> str | None:
    return economy_buy(game, coins)


def step_five(game: Game, coins: int, counts: dict[str, int]) -> str | None:
    return five_cost_buy(game, coins, counts, gardens_plan=False)


def step_four(game: Game, coins: int, counts: dict[str, int]) -> str | None:
    return four_cost_buy(game, coins, counts)


def step_three(game: Game, coins: int) -> str | None:
    return three_cost_buy(game, coins)

def step_last_resort_menu(game: Game, coins: int, counts: dict[str, int]) -> str | None:
    """
    Guarded priority menu; fully cost-aware; never buys copper.
    Silver only as a single glue copy when no engine piece is affordable.
    """
    cap = terminal_capacity(counts)
    engine_order = ["market","festival","laboratory","village","farmingvillage","port","poacher","smithy","councilroom","library"]
    for card in engine_order:
        if not in_stock(game, card):
            continue
        if card in ("smithy","councilroom","library") and cap <= 0:
            continue
        cost = COSTS.get(card, 99)
        if coins >= cost:
            return f"BUY {card}"

    # One Silver maximum, only if nothing else was affordable
    if counts.get("silver", 0) < 1 and in_stock(game, "silver") and coins >= COSTS.get("silver", 3):
        return "BUY silver"

    return None


# def step_last_resort_menu(game: Game, coins: int, counts: dict[str, int]) -> str | None:
#     """
#     A guarded priority menu to avoid 'END_TURN' with buy left.
#     Avoids Copper; prefers payload or safe terminals only if capacity allows.
#     """
#     # Respect terminal capacity before picking terminals.
#     cap = terminal_capacity(counts)

#     # Simple ordered pick-list by general usefulness at most boards.
#     # We gate terminal picks on cap and Smithy cap is already enforced upstream.
#     ordered = [
#         "market",  # +$ / +Buy / +Action
#         "festival",  # strong payload + actions
#         "laboratory",  # draw + action (non-terminal)
#         "village",  # unlock more terminals
#         "smithy",  # draw, but only if cap > 0
#         "silver",  # baseline economy if still in stock
#     ]

#     for card in ordered:
#         if not in_stock(game, card):
#             continue
#         if card == "smithy" and cap <= 0:
#             continue
#         # Check coin gates for treasures so we don't suggest unaffordable stuff
#         if card == "silver" and coins < BUY_SILVER_COINS:
#             continue
#         return f"BUY {card}"

#     return None


def choose_buy_action(game: Game, coins: int, me_idx: int, state: dict[str, object]) -> str:
    counts: dict[str, int] = state["counts"]  # type: ignore[assignment]
    provinces_left = game.stock.quantities.get("province", 0)
    my_score, best_opp = score_status(game, me_idx)
    gardens_plan = bool(state.get("gardens_plan", False))
    turn = int(state.get("turn", 1))
    ctx = BuyCtx(provinces_left=provinces_left, score_gap=my_score - best_opp, turn=turn)

    steps = (
        lambda: step_opening(game, coins, counts, turn),
        lambda: step_province_if_ok(game, coins, counts, ctx),
        lambda: step_gold_if_building(game, coins, counts, ctx),
        lambda: step_vp_override(game, coins, ctx),  # NEW: more aggressive greening window
        lambda: step_endgame(game, coins, ctx, my_score, best_opp),
        lambda: step_midgame(game, coins, ctx, my_score, best_opp),
        lambda: step_gardens_primary(game, coins, gardens_plan),
        lambda: step_gardens_secondary(game, coins, counts, gardens_plan),
        lambda: step_silver_floor(game, coins, counts, turn),  # NEW: baseline economy
        lambda: step_economy(game, coins),  # prefer Gold first
        lambda: six_cost_buy(game, coins, counts, turn),  # 6-cost after Gold
        lambda: step_five(game, coins, counts),
        lambda: step_four(game, coins, counts),
        lambda: step_three(game, coins),
        lambda: step_last_resort_menu(game, coins, counts),  # NEW: last resort menu (no Copper)
    )
    for s in steps:
        d = s()
        if d:
            return d

    if gardens_plan and in_stock(game, "copper"):
        extra_buys = int(state.get("extra_buys", 0))
        buys_left = int(state.get("buys_left", 1))
        if (extra_buys > 0 or buys_left > 1) or turn >= 18:
            return "BUY copper"

    return "END_TURN"
