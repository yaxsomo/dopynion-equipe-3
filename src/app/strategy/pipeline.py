from __future__ import annotations

from dopynion.data_model import Game

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
    BUY_PROVINCE_COINS,
)
from .state import BuyCtx
from .utils import in_stock, score_status


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
    if coins >= BUY_PROVINCE_COINS and in_stock(game, "gold"):
        if not early_province_ok(counts, ctx.provinces_left, ctx.turn, ctx.score_gap):
            return "BUY gold"
    return None


def step_endgame(game: Game, coins: int, ctx: BuyCtx, my_score: int, best_opp: int) -> str | None:
    return endgame_buy(game, coins, ctx.provinces_left, my_score, best_opp, ctx.turn)


def step_midgame(game: Game, coins: int, ctx: BuyCtx, my_score: int, best_opp: int) -> str | None:
    return midgame_buy(game, coins, ctx.provinces_left, my_score, best_opp, ctx.turn)


def step_gardens_primary(game: Game, coins: int, gardens_plan: bool) -> str | None:
    if gardens_plan and coins >= 4 and in_stock(game, "gardens"):
        return "BUY gardens"
    return None


def step_gardens_secondary(
    game: Game, coins: int, counts: dict[str, int], gardens_plan: bool
) -> str | None:
    if not gardens_plan:
        return None
    return five_cost_buy(game, coins, counts, gardens_plan=True)


def step_economy(game: Game, coins: int) -> str | None:
    return economy_buy(game, coins)


def step_five(game: Game, coins: int, counts: dict[str, int]) -> str | None:
    return five_cost_buy(game, coins, counts, gardens_plan=False)


def step_four(game: Game, coins: int, counts: dict[str, int]) -> str | None:
    return four_cost_buy(game, coins, counts)


def step_three(game: Game, coins: int) -> str | None:
    return three_cost_buy(game, coins)


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
        lambda: step_endgame(game, coins, ctx, my_score, best_opp),
        lambda: step_midgame(game, coins, ctx, my_score, best_opp),
        lambda: step_gardens_primary(game, coins, gardens_plan),
        lambda: step_gardens_secondary(game, coins, counts, gardens_plan),
        lambda: step_economy(game, coins),  # prefer Gold first
        lambda: six_cost_buy(game, coins, counts, turn),  # 6-cost after Gold
        lambda: step_five(game, coins, counts),
        lambda: step_four(game, coins, counts),
        lambda: step_three(game, coins),
    )
    for s in steps:
        d = s()
        if d:
            return d
    return "END_TURN"
