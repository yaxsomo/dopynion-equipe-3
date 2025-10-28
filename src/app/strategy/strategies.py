from __future__ import annotations

from collections.abc import Callable

from dopynion.data_model import Game

from . import pipeline  # reuse baseline steps
from .constants import (
    BUY_4_COST_COINS,
    BUY_5_COST_COINS,
    BUY_GOLD_COINS,
    BUY_PROVINCE_COINS,
    BUY_SILVER_COINS,
    ENDGAME_PROVINCE_THRESHOLD,
    MAX_SMITHIES,
    RUSH_TURN,
)
from .utils import in_stock, terminal_capacity

# === Strategy: combo_engine (draw + actions focus, no copper) ================
from .utils import in_stock, terminal_capacity, score_status
from .constants import (
    BUY_PROVINCE_COINS, BUY_GOLD_COINS, BUY_5_COST_COINS, BUY_4_COST_COINS, BUY_SILVER_COINS,
    MIN_GREEN_TURN, MIDGAME_PROVINCE_THRESHOLD, ENDGAME_PROVINCE_THRESHOLD, RUSH_TURN, MAX_SMITHIES, COSTS
)

# === Strategy: combo_engine (draw + actions focus, no copper) ================
from .utils import in_stock, terminal_capacity, score_status
from .constants import (
    COSTS,
    BUY_PROVINCE_COINS, BUY_GOLD_COINS, BUY_5_COST_COINS, BUY_4_COST_COINS
)

def _combo_engine(game, coins: int, me_idx: int, state: dict[str, object]) -> str:
    """
    Goals:
      - Never buy Copper.
      - Build max combos: prioritize +Actions +Cards first (cheap -> expensive), then +Actions/+Cards/+Coins (Market/Festival).
      - Mirror Witch if an opponent has one and curses remain (<= 2 copies, only with capacity).
      - Use Bandit as a Gold source (<= 2) only after we have action capacity / stable engine.
      - Keep Silver to at most 1 and only when no engine piece at that price.
      - Avoid Militia/Silver spam.
    """
    counts: dict[str, int] = state["counts"]  # type: ignore[assignment]
    turn = int(state.get("turn", 1))
    cap = terminal_capacity(counts)

    provinces_left = int(game.stock.quantities.get("province", 0))
    curses_left = int(state.get("curses_left", game.stock.quantities.get("curse", 0)))
    opp_has_witch = bool(state.get("opp_has_witch", False))

    # Current supply (booleans for readability)
    has = lambda c: in_stock(game, c)
    has_village = has("village")
    has_fvillage = has("farmingvillage")
    has_port    = has("port")
    has_poacher = has("poacher")
    has_market  = has("market")
    has_labo    = has("laboratory")
    has_fest    = has("festival")
    has_smithy  = has("smithy")
    has_croom   = has("councilroom")
    has_library = has("library")
    has_bandit  = has("bandit")
    has_witch   = has("witch")
    has_chapel  = has("chapel")
    has_workshop= has("workshop")
    has_remodel = has("remodel")

    # Deck shape
    terminals = (
        counts.get("smithy",0) + counts.get("witch",0) + counts.get("militia",0) +
        counts.get("bandit",0) + counts.get("bureaucrat",0) + counts.get("chancellor",0) +
        counts.get("councilroom",0) + counts.get("library",0) + counts.get("adventurer",0)
    )
    plus_actions = (
        counts.get("village",0) + counts.get("market",0) + counts.get("festival",0) +
        counts.get("farmingvillage",0) + counts.get("port",0) + counts.get("poacher",0) +
        counts.get("laboratory",0)   # non-terminal draw contributes 1 capacity in our heuristic
    )
    deficit = max(0, terminals - plus_actions)

    engine_stable = (
        (counts.get("market",0)+counts.get("laboratory",0)+counts.get("festival",0)) >= 3
        or ( (counts.get("village",0)+counts.get("farmingvillage",0)+counts.get("port",0)) >= 2
             and (counts.get("smithy",0)+counts.get("councilroom",0)+counts.get("library",0)) >= 1 )
    )

    # --- Provinces only when appropriate (late/low or stable engine/ahead)
    my_score, opp_best = score_status(game, me_idx)
    if coins >= BUY_PROVINCE_COINS and has("province"):
        if provinces_left <= 5 or engine_stable or turn >= 10 or (my_score - opp_best) >= 6:
            return "BUY province"

    # --- Early trashing: Chapel opening if present
    if has_chapel and counts.get("chapel",0) < 1 and coins in (2,3,4) and turn <= 2:
        return "BUY chapel"

    # --- Mirror Witch if opponent bought it and curses remain (<= 2 copies; needs capacity)
    if coins >= BUY_5_COST_COINS and has_witch and opp_has_witch and curses_left > 0 and counts.get("witch",0) < 2 and cap > 0:
        return "BUY witch"

    # --- Fix action deficit first with the CHEAPEST +actions/+cards
    if deficit > 0:
        if coins >= BUY_4_COST_COINS:
            # Start cheap and plentiful
            for c in ("village", "farmingvillage", "port"):
                if has(c): return f"BUY {c}"
            if has_poacher: return "BUY poacher"
        if coins >= BUY_5_COST_COINS:
            # Then the 5-cost engines (prefer Market, then Festival, then Laboratory)
            for c in ("market", "festival", "laboratory"):
                if has(c): return f"BUY {c}"

    # --- Core engine growth (no deficit): add non-terminal draw & cantrips
    if coins >= BUY_5_COST_COINS:
        for c in ("market", "laboratory", "festival"):
            if has(c): return f"BUY {c}"
    if coins >= BUY_4_COST_COINS:
        for c in ("poacher", "port", "village", "farmingvillage"):
            if has(c): return f"BUY {c}"

    # --- Single terminal draw only when we have capacity
    if cap > 0 and coins >= BUY_4_COST_COINS:
        for c in ("smithy", "councilroom", "library"):
            if has(c):
                # Library can anti-synergize with many actions; limit to 1
                if c == "library" and counts.get("library",0) >= 1:
                    continue
                return f"BUY {c}"

    # --- Economy w/o killing the engine
    # Optional openers to gain engine parts
    if turn <= 3 and coins >= 3 and has_workshop and counts.get("workshop",0) < 1:
        return "BUY workshop"
    if turn <= 4 and coins >= 4 and has_remodel and counts.get("remodel",0) < 1:
        return "BUY remodel"

    # Bandit as a Gold source once we have capacity / some stability
    if coins >= BUY_5_COST_COINS and has_bandit and cap > 0 and counts.get("bandit",0) < 2 and (engine_stable or plus_actions >= 2):
        return "BUY bandit"

    # Gold at 6 only once we have at least some engine
    if coins >= BUY_GOLD_COINS and (plus_actions >= 2 or engine_stable) and has("gold"):
        return "BUY gold"

    # One Silver maximum as glue at 3–4 when no engine card is available
    if coins in (3,4) and counts.get("silver",0) < 1 and not any([
        (coins >= BUY_4_COST_COINS and (has_village or has_fvillage or has_port or has_poacher)),
        (coins >= BUY_5_COST_COINS and (has_market or has_labo or has_fest))
    ]) and has("silver"):
        return "BUY silver"

    # Last resort: any engine piece we can afford (NEVER copper)
    for c in ("market","laboratory","festival","village","farmingvillage","port","poacher","smithy","councilroom","library","silver","gold"):
        if has(c) and coins >= COSTS.get(c, 99):
            # still avoid terminal draw if no capacity
            if c in ("smithy","councilroom","library") and cap <= 0:
                continue
            # avoid extra silver if we already have one and any engine is present
            if c == "silver" and counts.get("silver",0) >= 1:
                continue
            return f"BUY {c}"

    return "END_TURN"


# ---- Strategy signature ----
BuyFn = Callable[[Game, int, int, dict[str, object]], str]


def _vp_pressure_fallback(game: Game, coins: int, turn: int) -> str | None:
    """Generic greening fallback used by several strategies."""
    provinces_left = game.stock.quantities.get("province", 0)
    if coins >= BUY_PROVINCE_COINS and in_stock(game, "province"):
        if provinces_left <= ENDGAME_PROVINCE_THRESHOLD or turn >= (RUSH_TURN - 3):
            return "BUY province"
    if coins >= BUY_5_COST_COINS and in_stock(game, "duchy"):
        if provinces_left <= ENDGAME_PROVINCE_THRESHOLD or turn >= (RUSH_TURN - 1):
            return "BUY duchy"
    if coins >= 2 and in_stock(game, "estate") and (provinces_left <= 2 or turn >= RUSH_TURN):
        return "BUY estate"
    return None


# === Strategy: Big Money / Smithy ===========================================


def _bm_smithy(game: Game, coins: int, me_idx: int, state: dict[str, object]) -> str:
    """Simple: 2x Smithy max, otherwise money → VP."""
    counts: dict[str, int] = state["counts"]  # type: ignore[assignment]
    turn = int(state.get("turn", 1))

    # Provinces/VP first if late
    vp = _vp_pressure_fallback(game, coins, turn)
    if vp:
        return vp

    # Province at 8 when available
    if coins >= BUY_PROVINCE_COINS and in_stock(game, "province"):
        return "BUY province"

    # Gold at 6+
    if coins >= BUY_GOLD_COINS and in_stock(game, "gold"):
        return "BUY gold"

    # Exactly 5: prioritize first/second Smithy (cap)
    if coins >= BUY_5_COST_COINS and counts.get("smithy", 0) < 2 and in_stock(game, "smithy"):
        return "BUY smithy"

    # Otherwise at 5: Duchy (light pressure) or Laboratory if available
    if coins >= BUY_5_COST_COINS:
        if in_stock(game, "laboratory"):
            return "BUY laboratory"
        if in_stock(game, "duchy"):
            return "BUY duchy"

    # Silver on 3 to 4
    if coins >= BUY_SILVER_COINS and in_stock(game, "silver"):
        return "BUY silver"

    # Village/Smithy not used here; last resort: Estate if very late
    return "END_TURN"


# === Strategy: Village / Smithy engine ======================================


def _village_smithy(game: Game, coins: int, me_idx: int, state: dict[str, object]) -> str:
    """
    Alternate Village / Smithy up to healthy caps, maintain economy, and green.
    Targets (soft): Villages ~6, Smithies ~5.
    """
    counts: dict[str, int] = state["counts"]  # type: ignore[assignment]
    turn = int(state.get("turn", 1))
    cap = terminal_capacity(counts)

    vp = _vp_pressure_fallback(game, coins, turn)
    if vp:
        return vp

    # Province early if we can support it
    if coins >= BUY_PROVINCE_COINS and in_stock(game, "province"):
        return "BUY province"

    # Gold at 6 to keep economy flowing
    if coins >= BUY_GOLD_COINS and in_stock(game, "gold"):
        return "BUY gold"

    # At 5: take Smithy only if capacity allows and cap not exceeded
    if coins >= BUY_5_COST_COINS:
        # Prefer Laboratory/Market/Festival if available (safer)
        for c in ("laboratory", "market", "festival"):
            if in_stock(game, c):
                return f"BUY {c}"
        if cap > 0 and counts.get("smithy", 0) < 5 and in_stock(game, "smithy"):
            return "BUY smithy"
        if in_stock(game, "duchy") and turn >= (RUSH_TURN - 4):
            return "BUY duchy"

    # At 4: keep Village supply coming (soft cap ~6)
    if coins >= BUY_4_COST_COINS:
        if in_stock(game, "village") and counts.get("village", 0) < 6:
            return "BUY village"
        for c in ("moneylender", "militia", "remodel", "remake", "port", "poacher"):
            if in_stock(game, c):
                return f"BUY {c}"

    # 3 to 4 Silver floor to avoid stalling
    if coins >= BUY_SILVER_COINS and in_stock(game, "silver"):
        return "BUY silver"

    return "END_TURN"


# === Strategy: Militia + Market counter =====================================


def _militia_market_counter(game: Game, coins: int, me_idx: int, state: dict[str, object]) -> str:
    """
    Counter fast draw engines: 1x Militia, 1x Gold (max), up to 5 Markets,
    then up to 5 Smithies and 6 Villages, 1x Cellar. Then green.
    """
    counts: dict[str, int] = state["counts"]  # type: ignore[assignment]
    turn = int(state.get("turn", 1))
    cap = terminal_capacity(counts)

    vp = _vp_pressure_fallback(game, coins, turn)
    if vp:
        return vp

    if coins >= BUY_PROVINCE_COINS and in_stock(game, "province"):
        return "BUY province"

    # Exactly one Gold
    have_gold = counts.get("gold", 0) >= 1

    # Ensure 1 Militia
    if counts.get("militia", 0) == 0 and coins >= BUY_4_COST_COINS and in_stock(game, "militia"):
        return "BUY militia"

    # Markets (up to 5)
    if coins >= BUY_5_COST_COINS and counts.get("market", 0) < 5 and in_stock(game, "market"):
        return "BUY market"

    # Single Gold at 6 first time we see 6 coins
    if not have_gold and coins >= BUY_GOLD_COINS and in_stock(game, "gold"):
        return "BUY gold"

    # Then Smithies (up to 5) with capacity
    if (
        coins >= BUY_5_COST_COINS
        and counts.get("smithy", 0) < 5
        and cap > 0
        and in_stock(game, "smithy")
    ):
        return "BUY smithy"

    # Villages (up to 6)
    if coins >= BUY_4_COST_COINS and counts.get("village", 0) < 6 and in_stock(game, "village"):
        return "BUY village"

    # One Cellar at 2 if we don't have it
    if coins >= 2 and counts.get("cellar", 0) == 0 and in_stock(game, "cellar"):
        return "BUY cellar"

    # Economy
    if coins >= BUY_GOLD_COINS and in_stock(game, "gold"):
        return "BUY gold"
    if coins >= BUY_SILVER_COINS and in_stock(game, "silver"):
        return "BUY silver"

    return "END_TURN"


# === Strategy: Remodel + Market engine ======================================


def _remodel_market_engine(game: Game, coins: int, me_idx: int, state: dict[str, object]) -> str:
    """
    Open Remodel/Silver if possible; aim for:
    - 2 Gold (can remodel → Province later),
    - 1 Militia,
    - up to 4 Markets,
    - Villages + Smithies as needed (Smithy cap respected),
    - 1 Cellar.
    Then green with standard pressure.
    (We don't implement in-turn remodel plays here; only buys.)
    """
    counts: dict[str, int] = state["counts"]  # type: ignore[assignment]
    turn = int(state.get("turn", 1))
    cap = terminal_capacity(counts)

    vp = _vp_pressure_fallback(game, coins, turn)
    if vp:
        return vp

    if coins >= BUY_PROVINCE_COINS and in_stock(game, "province"):
        return "BUY province"

    # Ensure at least one Remodel early
    if counts.get("remodel", 0) == 0 and coins >= BUY_4_COST_COINS and in_stock(game, "remodel"):
        return "BUY remodel"

    # 2 Golds plan
    if counts.get("gold", 0) < 2 and coins >= BUY_GOLD_COINS and in_stock(game, "gold"):
        return "BUY gold"

    # 1 Militia
    if counts.get("militia", 0) == 0 and coins >= BUY_4_COST_COINS and in_stock(game, "militia"):
        return "BUY militia"

    # Markets up to 4
    if coins >= BUY_5_COST_COINS and counts.get("market", 0) < 4 and in_stock(game, "market"):
        return "BUY market"

    # Cellar once
    if counts.get("cellar", 0) == 0 and coins >= 2 and in_stock(game, "cellar"):
        return "BUY cellar"

    # Villages to support terminals
    if coins >= BUY_4_COST_COINS and in_stock(game, "village"):
        return "BUY village"

    # Smithy when capacity allows and cap not exceeded
    if (
        coins >= BUY_5_COST_COINS
        and cap > 0
        and counts.get("smithy", 0) < MAX_SMITHIES
        and in_stock(game, "smithy")
    ):
        return "BUY smithy"

    # Economy fallback
    if coins >= BUY_GOLD_COINS and in_stock(game, "gold"):
        return "BUY gold"
    if coins >= BUY_SILVER_COINS and in_stock(game, "silver"):
        return "BUY silver"

    return "END_TURN"


# ===== Registry =============================================================

STRATEGY_BUYERS: dict[str, BuyFn] = {
    "baseline": pipeline.choose_buy_action,  # your improved default
    "bm_smithy": _bm_smithy,
    "village_smithy": _village_smithy,
    "militia_market_counter": _militia_market_counter,
    "remodel_market_engine": _remodel_market_engine,
    "combo_engine": _combo_engine,
}


def choose_buy_action_for_strategy(
    strategy_key: str, game: Game, coins: int, me_idx: int, state: dict[str, object]
) -> str:
    buyer = STRATEGY_BUYERS.get(strategy_key, pipeline.choose_buy_action)
    return buyer(game, coins, me_idx, state)
