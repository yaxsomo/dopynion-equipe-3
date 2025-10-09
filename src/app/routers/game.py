from __future__ import annotations

from collections import defaultdict
from typing import Annotated, NamedTuple

from dopynion.data_model import (
    CardName,
    CardNameAndHand,
    Game,
    Hand,
    MoneyCardsInHand,
    PossibleCards,
)
from fastapi import APIRouter, Depends, Header, Request
from pydantic import BaseModel

from app.inspectors import (
    log_card_name_and_hand,
    log_context,
    log_decision,
    log_game_compact,
    log_hand,
    log_meta,
    log_money_cards,
    log_possible_cards,
    log_turn_state,
)


class BuyCtx(NamedTuple):
    provinces_left: int
    score_gap: int
    turn: int


# Track whether we've already bought during the current turn for each game
TURN_STATE: dict[str, dict[str, object]] = defaultdict(
    lambda: {"bought": False, "counts": defaultdict(int)}
)
ENGINE_ACTIONS = {"village", "market", "laboratory", "festival"}
TERMINAL_ACTIONS = {"smithy", "woodcutter"}  # simple terminals present in this set


def _get_state(game_id: str) -> dict[str, object]:
    """Return mutable per-game state dict with keys: 'bought' (bool), 'counts' (defaultdict)."""
    state = TURN_STATE[game_id]
    # ensure 'counts' exists and is a defaultdict(int)
    if "counts" not in state or not isinstance(state["counts"], defaultdict):
        state["counts"] = defaultdict(int)
    return state


def _score_status(game: Game, me_idx: int) -> tuple[int, int]:
    """Return (my_score, best_opponent_score)."""
    my_score = getattr(game.players[me_idx], "score", 0) or 0
    opp_scores = [getattr(p, "score", 0) or 0 for i, p in enumerate(game.players) if i != me_idx]
    return my_score, (max(opp_scores) if opp_scores else 0)


def _terminal_capacity(state_counts: dict[str, int]) -> int:
    """Approximate how many more terminal actions we can support without collision."""
    terminals = sum(state_counts.get(t, 0) for t in TERMINAL_ACTIONS)
    # sources of +Actions (very rough model)
    plus_actions = (
        state_counts.get("village", 0) * 2
        + state_counts.get("market", 0) * 1
        + state_counts.get("festival", 0) * 2
        + state_counts.get("laboratory", 0) * 1  # lab is non-terminal (+1 action)
    )
    # one native action per turn
    return 1 + plus_actions - terminals


# Our team name as exposed by /name; used to locate our player seat dynamically
TEAM_NAME = "Equipe3MaGueule"

router = APIRouter()
# ----- buying thresholds (avoid magic numbers) -----
BUY_PROVINCE_COINS = 8
BUY_GOLD_COINS = 6
BUY_5_COST_COINS = 5
BUY_4_COST_COINS = 4
BUY_SILVER_COINS = 3

# --- phase thresholds & caps (avoid magic numbers) ---
ENDGAME_PROVINCE_THRESHOLD = 2
MIDGAME_PROVINCE_THRESHOLD = 4

# --- turn-limit related knobs ---
MAX_TURN = 155  # hard stop by server
RUSH_TURN = 145  # start prioritizing VP to avoid leaving points on table
MIN_GREEN_TURN = 14  # avoid Provinces before this unless conditions force it
# Pace Provinces so we don't end the game too quickly while engine is small
PROVINCE_SOFT_CAP_BEFORE_TURN = 20
PROVINCES_ALLOWED_BEFORE_CAP = 2

MAX_LABS = 3
MAX_SMITHIES = 2

# --- lint-friendly thresholds (remove magic numbers) ---
ENGINE_GOLD_THRESHOLD = 2
ENGINE_LAB_THRESHOLD = 2
ENGINE_MF_SUM_THRESHOLD = 2
MIN_COPPER_TRASH = 2
OPENING_TURN_LIMIT = 3
COINS_EQ_3 = 3
COINS_EQ_4 = 4
COINS_EQ_5 = 5

# --- additional strategic thresholds ---
BEHIND_DUCHY_DEFICIT = 6  # if trailing by >= this, consider Duchy earlier
EARLY_PROVINCE_STOCK = 6  # start pressuring Provinces once <= this remain
GARDENS_EARLY_STOCK = 8  # consider Gardens plan if Provinces are plentiful

# --- costs and per-action bonuses (per client rules) ---
#
# Expanded cost table for more cards.
COSTS: dict[str, int] = {
    "province": 8,
    "duchy": 5,
    "estate": 2,
    "gold": 6,
    "silver": 3,
    "copper": 0,
    # core engine & economy
    "laboratory": 5,
    "market": 5,
    "festival": 5,
    "village": 3,
    "smithy": 4,
    "woodcutter": 3,
    "port": 4,
    "poacher": 4,
    "cellar": 2,
    "farmingvillage": 4,
    # alt-vp / payload helpers
    "gardens": 4,
    # trashers / gainers / attacks
    "chapel": 2,
    "moneylender": 4,
    "remodel": 4,
    "remake": 4,
    "workshop": 3,
    "feast": 4,
    "mine": 5,
    "witch": 5,
    "militia": 4,
    "bandit": 5,
    "bureaucrat": 4,
    # drawers / others (implemented in dopynion)
    "councilroom": 5,
    "library": 5,
    "adventurer": 6,
    "magpie": 4,
    "hireling": 6,
    "distantshore": 6,
    "marquis": 6,
}

# Bonus coins granted by *playing* these actions during the turn
ACTION_COIN_BONUS: dict[str, int] = {
    "market": 1,
    "festival": 2,
    "woodcutter": 2,
    "moneylender": 3,  # +3 coins when it trashes Copper
    "chancellor": 2,
    "poacher": 1,
    "farmingvillage": 2,
}

# Extra actions granted by playing an action
ACTION_PLUS_ACTIONS: dict[str, int] = {
    "village": 2,
    "market": 1,
    "laboratory": 1,
    "festival": 2,
    "port": 2,
    "cellar": 1,
    "farmingvillage": 2,
    "distantshore": 1,
    "magpie": 1,
    "poacher": 1,
}

# Extra buys granted by *playing* these actions during the turn
ACTION_BUY_BONUS: dict[str, int] = {
    "market": 1,
    "woodcutter": 1,
    "festival": 1,
    "councilroom": 1,
}

# --- helpers ---


def _in_stock(_game: Game, card: str) -> bool:
    return (_game.stock.quantities or {}).get(card, 0) > 0


def _early_province_ok(
    counts: dict[str, int],
    provinces_left: int,
    turn: int,
    score_gap: int,
) -> bool:
    result = False
    # Hard push near the turn cap: don't risk leaving VP on the table
    if turn >= RUSH_TURN:
        result = True
    # If Provinces are already low, it's okay to take them
    elif provinces_left <= EARLY_PROVINCE_STOCK:
        result = True
    # If our deck is strong, greening early is fine
    elif _engine_ready(counts):
        result = True
    # General build window: before MIN_GREEN_TURN, avoid Provinces unless we're far behind
    elif turn < MIN_GREEN_TURN and score_gap > -BEHIND_DUCHY_DEFICIT:
        result = False
    else:
        my_provinces = counts.get("province", 0)
        # Province pacing: before a certain turn, limit how many Provinces we personally take
        if turn < PROVINCE_SOFT_CAP_BEFORE_TURN and my_provinces >= PROVINCES_ALLOWED_BEFORE_CAP:
            result = False
        # If we're significantly behind, allow early Provinces as catch-up VP
        elif score_gap <= -BEHIND_DUCHY_DEFICIT:
            result = True
        # After the minimum green turn, it's acceptable
        elif turn >= MIN_GREEN_TURN:
            result = True
    return result


def _compute_treasure_coins(game: Game, me_idx: int) -> int:
    """Return coins from treasure cards currently in hand (no action bonuses)."""
    me = game.players[me_idx]
    q = (me.hand.quantities if me.hand else {}) or {}
    return q.get("copper", 0) * 1 + q.get("silver", 0) * 2 + q.get("gold", 0) * 3


def _engine_ready(counts: dict[str, int]) -> bool:
    """Heuristic: our deck is strong enough to start greening (reaching $8 consistently)."""
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


# ---- action sub-pickers to reduce branching ----


def _act_trashing(q: dict[str, int], actions_left: int, state: dict[str, object]) -> str | None:
    has_junk = (
        q.get("curse", 0) > 0 or q.get("estate", 0) > 0 or q.get("copper", 0) >= MIN_COPPER_TRASH
    )
    if q.get("chapel", 0) > 0 and has_junk:
        state["actions_left"] = actions_left - 1 + ACTION_PLUS_ACTIONS.get("chapel", 0)
        return "ACTION chapel"
    if q.get("moneylender", 0) > 0 and q.get("copper", 0) > 0:
        state["actions_left"] = actions_left - 1
        bonus = ACTION_COIN_BONUS.get("moneylender", 0)
        state["action_coins"] = int(state.get("action_coins", 0)) + bonus
        return "ACTION moneylender"
    if q.get("remodel", 0) > 0 or q.get("remake", 0) > 0:
        use = "remake" if q.get("remake", 0) > 0 else "remodel"
        state["actions_left"] = actions_left - 1
        return f"ACTION {use}"
    return None


def _act_nonterminal(q: dict[str, int], actions_left: int, state: dict[str, object]) -> str | None:
    order = (
        "village",
        "market",
        "laboratory",
        "festival",
        "distantshore",
        "port",
        "cellar",
        "farmingvillage",
        "magpie",
        "poacher",
    )
    for c in order:
        if q.get(c, 0) > 0:
            state["actions_left"] = actions_left - 1 + ACTION_PLUS_ACTIONS.get(c, 0)
            coin_bonus = ACTION_COIN_BONUS.get(c, 0)
            buy_bonus = ACTION_BUY_BONUS.get(c, 0)
            state["action_coins"] = int(state.get("action_coins", 0)) + coin_bonus
            state["extra_buys"] = int(state.get("extra_buys", 0)) + buy_bonus
            return f"ACTION {c}"
    return None


def _act_attacks(q: dict[str, int], actions_left: int, state: dict[str, object]) -> str | None:
    for c in ("witch", "militia", "bandit", "bureaucrat"):
        if q.get(c, 0) > 0:
            state["actions_left"] = actions_left - 1
            return f"ACTION {c}"
    return None


def _act_terminal_draw(
    q: dict[str, int],
    actions_left: int,
    state: dict[str, object],
) -> str | None:
    for c in ("councilroom", "smithy", "library", "adventurer"):
        if q.get(c, 0) > 0:
            state["actions_left"] = actions_left - 1
            coin_bonus = ACTION_COIN_BONUS.get(c, 0)
            buy_bonus = ACTION_BUY_BONUS.get(c, 0)
            state["action_coins"] = int(state.get("action_coins", 0)) + coin_bonus
            state["extra_buys"] = int(state.get("extra_buys", 0)) + buy_bonus
            return f"ACTION {c}"
    return None


def _act_economy(q: dict[str, int], actions_left: int, state: dict[str, object]) -> str | None:
    for c in ("mine", "feast", "workshop"):
        if q.get(c, 0) > 0:
            state["actions_left"] = actions_left - 1
            return f"ACTION {c}"
    return None


# New helper: action selection logic
def choose_action(game: Game, me_idx: int, state: dict[str, object]) -> str | None:
    """Decide which ACTION to play this call, if any."""
    me = game.players[me_idx]
    q = (me.hand.quantities if me.hand else {}) or {}

    actions_left = int(state.get("actions_left", 1))
    if actions_left <= 0:
        return None

    # quickly check if any actionable card exists
    actionable = [
        k
        for k in q
        if k in COSTS and k not in {"copper", "silver", "gold", "estate", "duchy", "province"}
    ]
    if not actionable:
        return None

    # Try sub-pickers in order
    for picker in (_act_trashing, _act_nonterminal, _act_attacks, _act_terminal_draw, _act_economy):
        decision = picker(q, actions_left, state)
        if decision is not None:
            return decision

    return None


FIVE_COST_PREFER = ["laboratory", "market", "festival"]
FOUR_COST_PREFER = ["village", "smithy"]  # default preference; smithy gated by terminal capacity
# crude priority table (higher is better)
CARD_PRIORITY = defaultdict(
    lambda: 0,
    {
        "province": 100,
        "gold": 80,
        "laboratory": 70,
        "market": 62,
        "festival": 58,
        "smithy": 55,
        "village": 40,
        "duchy": 35,
        "gardens": 32,
        "silver": 30,
        "estate": 10,
        "copper": 5,
    },
)

JUNK = {"estate", "curse"}


def _best_from(options: list[CardName]) -> CardName:
    # pick the highest-priority option; tie-breaker = alphabetical for stability
    return sorted(options, key=lambda c: (-CARD_PRIORITY[c], c))[0]


def _worst_in_hand(hand: list[CardName]) -> CardName:
    # prefer to discard/trash junk > copper > low actions
    # score = lower is worse
    def score(c: CardName) -> tuple[int, int]:
        if c in JUNK:  # estates, curses are worst
            return (0, CARD_PRIORITY[c])
        if c == "copper":
            return (1, CARD_PRIORITY[c])
        # everything else: keep, but prefer to lose lowest-priority
        return (2, CARD_PRIORITY[c])

    return sorted(hand, key=lambda c: score(c))[0]


# -----------------------------
# Response models (legacy style)
# -----------------------------
class DopynionResponseBool(BaseModel):
    game_id: str
    decision: bool


class DopynionResponseCardName(BaseModel):
    game_id: str
    decision: CardName


class DopynionResponseStr(BaseModel):
    game_id: str
    decision: str


# -----------------------------
# Dependency: game id header
# -----------------------------
def get_game_id(x_game_id: str = Header(description="ID of the game")) -> str:
    return x_game_id


GameIdDependency = Annotated[str, Depends(get_game_id)]


# -----------------------------
# Routes (same paths as legacy)
# -----------------------------
@router.get("/name")
def name() -> str:
    return "Equipe3MaGueule"


@router.get("/start_game")
def start_game(game_id: GameIdDependency, request: Request) -> DopynionResponseStr:
    log_meta(request, game_id)
    return DopynionResponseStr(game_id=game_id, decision="OK")


@router.get("/start_turn")
def start_turn(game_id: GameIdDependency, request: Request) -> DopynionResponseStr:
    log_meta(request, game_id)
    state = _get_state(game_id)
    state["bought"] = False  # reset per turn
    # provisional defaults; will be set precisely in /play when hand is available
    state["buys_left"] = 1
    state["coins_left"] = 0
    state["initialized_resources"] = False
    state["phase"] = "ACTION"
    state["actions_left"] = 1
    state["action_coins"] = 0
    state["extra_buys"] = 0
    state["turn"] = int(state.get("turn", 0)) + 1
    log_decision(game_id, "OK")
    log_turn_state(game_id, state)
    return DopynionResponseStr(game_id=game_id, decision="OK")


def _find_me(game: Game) -> int:
    """Return the index of our bot in game.players.

    Strategy:
    1) Prefer a name match containing TEAM_NAME (the server prefixes our name with the base URL).
    2) If exactly one player currently has a hand, assume that's us.
    3) Fallback to index 1 if it exists, otherwise 0.
    """
    # 1) Name-based match (e.g., "[https://.../] Equipe3MaGueule (...)")
    for i, p in enumerate(game.players):
        if getattr(p, "name", None) and TEAM_NAME in p.name:
            return i

    # 2) Single player with a hand
    with_hand = [i for i, p in enumerate(game.players) if getattr(p, "hand", None)]
    if len(with_hand) == 1:
        return with_hand[0]

    # 3) Safe default
    return 1 if len(game.players) > 1 else 0


# --- strategic helpers for Gardens/alt-VP ---
def _score_gap(game: Game, me_idx: int) -> int:
    my, opp = _score_status(game, me_idx)
    return my - opp


def _should_pivot_to_gardens(game: Game, me_idx: int) -> bool:
    """Decide once per game if we should pursue a Gardens strategy.
    Conditions (approx):
      - Gardens pile exists
      - Provinces are plentiful (early/mid) to give time to grow deck
      - We are trailing by a noticeable amount (encourage alt-VP), or
        there are many +buy/+gain actions available.
    """
    if not _in_stock(game, "gardens"):
        return False
    provinces_left = game.stock.quantities.get("province", 0)
    if provinces_left < GARDENS_EARLY_STOCK:
        return False
    # If behind by 6+ VP, or if both Market and Festival exist (extra buys), consider Gardens.
    gap = _score_gap(game, me_idx)
    many_buys_avail = _in_stock(game, "market") or _in_stock(game, "festival")
    return gap <= -BEHIND_DUCHY_DEFICIT or many_buys_avail


def _endgame_buy(
    _game: Game, coins: int, provinces_left: int, my_score: int, best_opp: int, turn: int
) -> str | None:
    """Heuristics when piles are low or we're close to the turn limit."""
    decision: str | None = None
    # Near the turn cap, prioritize VP regardless of pile counts
    if turn >= RUSH_TURN:
        if coins >= BUY_PROVINCE_COINS and _game.stock.quantities.get("province", 0) > 0:
            decision = "BUY province"
        elif coins >= BUY_5_COST_COINS and _in_stock(_game, "duchy"):
            decision = "BUY duchy"
        elif coins >= BUY_SILVER_COINS and _in_stock(_game, "estate"):
            decision = "BUY estate"
        return decision

    if provinces_left <= ENDGAME_PROVINCE_THRESHOLD:
        if coins >= BUY_PROVINCE_COINS and _game.stock.quantities.get("province", 0) > 0:
            decision = "BUY province"
        elif coins >= BUY_5_COST_COINS and _in_stock(_game, "duchy"):
            decision = "BUY duchy"
        elif coins >= BUY_SILVER_COINS and _in_stock(_game, "estate"):
            decision = "BUY estate"
    return decision


def _midgame_buy(
    _game: Game, coins: int, provinces_left: int, my_score: int, best_opp: int, turn: int
) -> str | None:
    """Greening pressure before the final two provinces; turn pressure aware."""
    # If we're approaching the cap, start taking Provinces on $8 even in midgame
    if turn >= RUSH_TURN and coins >= BUY_PROVINCE_COINS and _in_stock(_game, "province"):
        return "BUY province"
    if provinces_left <= MIDGAME_PROVINCE_THRESHOLD:
        if coins >= BUY_PROVINCE_COINS and _in_stock(_game, "province"):
            return "BUY province"
        if coins >= BUY_5_COST_COINS and _in_stock(_game, "duchy") and my_score <= best_opp:
            return "BUY duchy"
    # Also, if significantly behind anytime and can afford Duchy, take it to catch up a bit
    if (
        (best_opp - my_score) >= BEHIND_DUCHY_DEFICIT
        and coins >= BUY_5_COST_COINS
        and _in_stock(_game, "duchy")
    ):
        return "BUY duchy"
    return None


def _economy_buy(_game: Game, coins: int) -> str | None:
    """Gold when we can afford it and provinces aren't forced."""
    if coins >= BUY_GOLD_COINS and _game.stock.quantities.get("gold", 0) > 0:
        return "BUY gold"
    return None


def _five_witch(_game: Game) -> bool:
    return _game.stock.quantities.get("curse", 0) > 0 and _in_stock(_game, "witch")


def _five_need_actions(counts: dict[str, int]) -> bool:
    return _terminal_capacity(counts) <= 0


def _five_wishlist_curses(_game: Game) -> list[str]:
    has_curses = _game.stock.quantities.get("curse", 0) > 0
    if has_curses and _in_stock(_game, "witch"):
        return ["witch"]
    return []


def _five_wishlist_labs(_game: Game, counts: dict[str, int]) -> list[str]:
    labs_ok = _in_stock(_game, "laboratory")
    need_lab = counts.get("laboratory", 0) < MAX_LABS
    if labs_ok and need_lab:
        return ["laboratory"]
    return []


def _five_wishlist_need_actions(_game: Game, counts: dict[str, int], coins: int) -> list[str]:
    picks: list[str] = []
    if _five_need_actions(counts):
        for c in ("market", "festival"):
            if _in_stock(_game, c):
                picks.append(c)
        if _in_stock(_game, "village") and coins >= BUY_4_COST_COINS:
            picks.append("village")
    return picks


def _five_wishlist_gardens_line(_game: Game, gardens_plan: bool) -> list[str]:
    if not gardens_plan:
        return []
    picks: list[str] = []
    for c in ("market", "festival", "laboratory"):
        if _in_stock(_game, c):
            picks.append(c)
    return picks


def _five_wishlist_defaults(_game: Game) -> list[str]:
    picks: list[str] = []
    for c in FIVE_COST_PREFER:
        if _in_stock(_game, c):
            picks.append(c)
    return picks


def _five_wishlist_fallback(_game: Game) -> list[str]:
    return ["silver"] if _in_stock(_game, "silver") else []


def _five_cost_buy(
    _game: Game, coins: int, counts: dict[str, int], gardens_plan: bool = False
) -> str | None:
    if coins < BUY_5_COST_COINS:
        return None

    wishlist: list[str] = []
    wishlist += _five_wishlist_curses(_game)
    wishlist += _five_wishlist_labs(_game, counts)
    wishlist += _five_wishlist_need_actions(_game, counts, coins)
    wishlist += _five_wishlist_gardens_line(_game, gardens_plan)
    wishlist += _five_wishlist_defaults(_game)
    wishlist += _five_wishlist_fallback(_game)

    for c in wishlist:
        return f"BUY {c}"
    return None


def _four_cost_buy(_game: Game, coins: int, counts: dict[str, int]) -> str | None:
    if coins < BUY_4_COST_COINS:
        return None
    decision: str | None = None
    for c in ("moneylender", "militia", "port", "poacher", "remodel", "remake"):
        if _in_stock(_game, c):
            decision = f"BUY {c}"
            break
    if decision is None and _terminal_capacity(counts) <= 0 and _in_stock(_game, "village"):
        decision = "BUY village"
    if decision is None and _in_stock(_game, "smithy"):
        decision = "BUY smithy"
    if decision is None and _in_stock(_game, "gardens"):
        decision = "BUY gardens"
    if decision is None and _in_stock(_game, "silver"):
        decision = "BUY silver"
    return decision


def _three_cost_buy(_game: Game, coins: int) -> str | None:
    if coins >= COINS_EQ_3:
        for c in ("workshop", "village", "woodcutter"):
            if _in_stock(_game, c):
                return f"BUY {c}"
        if _in_stock(_game, "silver"):
            return "BUY silver"
    return None


# New 6-cost action buy helper (before defaulting to Gold)
def _six_cost_buy(_game: Game, coins: int, counts: dict[str, int], turn: int) -> str | None:
    if coins < BUY_GOLD_COINS:
        return None
    # Hireling is strongest early since it pays off over many turns.
    have_hireling = counts.get("hireling", 0) > 0
    if _in_stock(_game, "hireling") and not have_hireling and turn <= (MIN_GREEN_TURN + 4):
        return "BUY hireling"
    # Distant Shore: non-terminal draw with +1 Action; good when engine-ready or early build.
    if _in_stock(_game, "distantshore"):
        if _engine_ready(counts) or turn <= MIN_GREEN_TURN:
            return "BUY distantshore"
    return None


def _opening_buy_5plus(_game: Game) -> str | None:
    if _game.stock.quantities.get("curse", 0) > 0 and _in_stock(_game, "witch"):
        return "BUY witch"
    for c in ("laboratory", "market", "festival", "councilroom"):
        if _in_stock(_game, c):
            return f"BUY {c}"
    return None


def _opening_buy_4(_game: Game) -> str | None:
    for c in ("moneylender", "militia", "smithy", "remodel", "remake", "poacher", "port"):
        if _in_stock(_game, c):
            return f"BUY {c}"
    if _in_stock(_game, "village"):
        return "BUY village"
    if _in_stock(_game, "silver"):
        return "BUY silver"
    return None


def _opening_buy_3(_game: Game) -> str | None:
    for c in ("workshop", "village", "woodcutter"):
        if _in_stock(_game, c):
            return f"BUY {c}"
    if _in_stock(_game, "silver"):
        return "BUY silver"
    return None


def _opening_buy_2(_game: Game, counts: dict[str, int]) -> str | None:
    if counts.get("chapel", 0) == 0 and _in_stock(_game, "chapel"):
        return "BUY chapel"
    if _in_stock(_game, "cellar"):
        return "BUY cellar"
    if _in_stock(_game, "estate"):
        return "BUY estate"
    return None


def _opening_buys(_game: Game, coins: int, counts: dict[str, int], turn: int) -> str | None:
    if turn > OPENING_TURN_LIMIT:
        return None
    if coins >= COINS_EQ_5:
        pick = _opening_buy_5plus(_game)
        if pick:
            return pick
    if coins == COINS_EQ_4:
        pick = _opening_buy_4(_game)
        if pick:
            return pick
    if coins == COINS_EQ_3:
        pick = _opening_buy_3(_game)
        if pick:
            return pick
    if coins == BUY_4_COST_COINS - 2:
        return _opening_buy_2(_game, counts)
    return None


def _step_opening(_game: Game, coins: int, counts: dict[str, int], turn: int) -> str | None:
    return _opening_buys(_game, coins, counts, turn)


def _step_province_if_ok(
    _game: Game, coins: int, counts: dict[str, int], ctx: BuyCtx
) -> str | None:
    if coins >= BUY_PROVINCE_COINS and _in_stock(_game, "province"):
        if _early_province_ok(counts, ctx.provinces_left, ctx.turn, ctx.score_gap):
            return "BUY province"
    return None


def _step_gold_if_building(
    _game: Game, coins: int, counts: dict[str, int], ctx: BuyCtx
) -> str | None:
    if coins >= BUY_PROVINCE_COINS and _in_stock(_game, "gold"):
        if not _early_province_ok(counts, ctx.provinces_left, ctx.turn, ctx.score_gap):
            return "BUY gold"
    return None


def _step_endgame(_game: Game, coins: int, ctx: BuyCtx, my_score: int, best_opp: int) -> str | None:
    return _endgame_buy(_game, coins, ctx.provinces_left, my_score, best_opp, ctx.turn)


def _step_midgame(_game: Game, coins: int, ctx: BuyCtx, my_score: int, best_opp: int) -> str | None:
    return _midgame_buy(_game, coins, ctx.provinces_left, my_score, best_opp, ctx.turn)


def _step_gardens_secondary(
    _game: Game, coins: int, counts: dict[str, int], gardens_plan: bool
) -> str | None:
    if not gardens_plan:
        return None
    return _five_cost_buy(_game, coins, counts, gardens_plan=True)


def _step_gardens_primary(_game: Game, coins: int, gardens_plan: bool) -> str | None:
    if gardens_plan and coins >= BUY_4_COST_COINS and _in_stock(_game, "gardens"):
        return "BUY gardens"
    return None


def _step_gardens_secondary(
    _game: Game,
    coins: int,
    counts: dict[str, int],
    gardens_plan: bool,
) -> str | None:
    if not gardens_plan:
        return None
    return _five_cost_buy(_game, coins, counts, gardens_plan=True)


def _step_economy(_game: Game, coins: int) -> str | None:
    return _economy_buy(_game, coins)


def _step_five(_game: Game, coins: int, counts: dict[str, int]) -> str | None:
    return _five_cost_buy(_game, coins, counts, gardens_plan=False)


def _step_four(_game: Game, coins: int, counts: dict[str, int]) -> str | None:
    return _four_cost_buy(_game, coins, counts)


def _step_three(_game: Game, coins: int) -> str | None:
    return _three_cost_buy(_game, coins)


def choose_buy_action(_game: Game, coins: int, me_idx: int, state: dict[str, object]) -> str:
    counts: defaultdict[str, int] = state["counts"]  # type: ignore[assignment]
    provinces_left = _game.stock.quantities.get("province", 0)
    my_score, best_opp = _score_status(_game, me_idx)
    gardens_plan = bool(state.get("gardens_plan", False))
    turn = int(state.get("turn", 1))
    ctx = BuyCtx(
        provinces_left=provinces_left,
        score_gap=my_score - best_opp,
        turn=turn,
    )

    steps = (
        lambda: _step_opening(_game, coins, counts, turn),
        lambda: _step_province_if_ok(_game, coins, counts, ctx),
        lambda: _step_gold_if_building(_game, coins, counts, ctx),
        lambda: _step_endgame(_game, coins, ctx, my_score, best_opp),
        lambda: _step_midgame(_game, coins, ctx, my_score, best_opp),
        lambda: _step_gardens_primary(_game, coins, gardens_plan),
        lambda: _step_gardens_secondary(_game, coins, counts, gardens_plan),
        lambda: _six_cost_buy(_game, coins, counts, turn),
        lambda: _step_economy(_game, coins),
        lambda: _step_five(_game, coins, counts),
        lambda: _step_four(_game, coins, counts),
        lambda: _step_three(_game, coins),
    )

    for s in steps:
        d = s()
        if d:
            return d
    return "END_TURN"


@router.post("/play")
def play(_game: Game, game_id: GameIdDependency, request: Request) -> DopynionResponseStr:
    log_meta(request, game_id)
    log_game_compact(_game)

    state = _get_state(game_id)
    me_idx = _find_me(_game)

    # Ensure defaults for new per-turn state keys
    state.setdefault("phase", "ACTION")
    state.setdefault("actions_left", 1)
    state.setdefault("action_coins", 0)
    state.setdefault("extra_buys", 0)
    state.setdefault("buys_left", 1)

    # Initialize/remember strategic long-term plan flags
    if "gardens_plan" not in state:
        state["gardens_plan"] = _should_pivot_to_gardens(_game, me_idx)

    log_turn_state(game_id, state)

    # --- ACTION phase handling ---
    if state.get("phase") == "ACTION":
        action_decision = choose_action(_game, me_idx, state)
        if action_decision is not None:
            log_context(
                game_id,
                phase="action",
                me_idx=me_idx,
                actions_left=state.get("actions_left"),
                chosen=action_decision,
            )
            log_decision(game_id, action_decision)
            return DopynionResponseStr(game_id=game_id, decision=action_decision)
        # no action to play -> transition to BUY
        state["phase"] = "BUY"

    # --- BUY phase handling ---
    treasure_coins = _compute_treasure_coins(_game, me_idx)
    coins_left = treasure_coins + int(state.get("action_coins", 0))
    buys_left = int(state.get("buys_left", 1)) + int(state.get("extra_buys", 0))
    state["coins_left"] = coins_left

    # If no buys remain or no meaningful buys affordable, end turn
    affordable_any = (
        (_game.stock.quantities.get("province", 0) > 0 and coins_left >= BUY_PROVINCE_COINS)
        or (_game.stock.quantities.get("gold", 0) > 0 and coins_left >= BUY_GOLD_COINS)
        or coins_left >= BUY_SILVER_COINS  # at least silver-tier options might exist
    )
    if buys_left <= 0 or not affordable_any:
        decision = "END_TURN"
        log_decision(game_id, decision)
        return DopynionResponseStr(game_id=game_id, decision=decision)

    # Delegated decision logic using remaining coins
    decision = choose_buy_action(_game, coins_left, me_idx, state)
    log_context(
        game_id,
        phase="buy",
        me_idx=me_idx,
        coins_left=coins_left,
        buys_left=buys_left,
        chosen=decision,
        gardens_plan=state.get("gardens_plan", False),
    )

    # Mark and update state after a buy
    if decision.startswith("BUY"):
        state["bought"] = True
        try:
            _, card = decision.split(" ", 1)
            card = card.strip().lower()
            cost = COSTS.get(card, 0)
            state["coins_left"] = max(0, coins_left - cost)
            # Only decrement base buys; leave extra_buys untouched
            state["buys_left"] = max(0, int(state.get("buys_left", 1)) - 1)

            counts: defaultdict[str, int] = state["counts"]  # type: ignore[assignment]
            counts[card] += 1
        except Exception:
            # keep state consistent even on parsing issues
            state["coins_left"] = coins_left
            state["buys_left"] = max(0, int(state.get("buys_left", 1)) - 1)

    log_decision(game_id, decision)
    return DopynionResponseStr(game_id=game_id, decision=decision)


@router.get("/end_game")
def end_game(game_id: GameIdDependency, request: Request) -> DopynionResponseStr:
    log_meta(request, game_id)
    TURN_STATE.pop(game_id, None)
    log_decision(game_id, "OK")
    return DopynionResponseStr(game_id=game_id, decision="OK")


@router.post("/confirm_discard_card_from_hand")
async def confirm_discard_card_from_hand(
    game_id: GameIdDependency,
    _decision_input: CardNameAndHand,
    request: Request,
) -> DopynionResponseBool:
    log_meta(request, game_id)
    log_card_name_and_hand(_decision_input)
    log_decision(game_id, "CONFIRM_DISCARD", {"card_name": _decision_input.card_name})
    return DopynionResponseBool(game_id=game_id, decision=True)


@router.post("/discard_card_from_hand")
async def discard_card_from_hand(
    game_id: GameIdDependency,
    decision_input: Hand,
    request: Request,
) -> DopynionResponseCardName:
    log_meta(request, game_id)
    log_hand(decision_input)
    pick = _worst_in_hand(decision_input.hand)
    log_decision(game_id, "DISCARD_FROM_HAND", {"chosen": pick})
    return DopynionResponseCardName(game_id=game_id, decision=pick)


@router.post("/confirm_trash_card_from_hand")
async def confirm_trash_card_from_hand(
    game_id: GameIdDependency,
    _decision_input: CardNameAndHand,
    request: Request,
) -> DopynionResponseBool:
    log_meta(request, game_id)
    log_card_name_and_hand(_decision_input)
    log_decision(game_id, "CONFIRM_TRASH", {"card_name": _decision_input.card_name})
    return DopynionResponseBool(game_id=game_id, decision=True)


@router.post("/trash_card_from_hand")
async def trash_card_from_hand(
    game_id: GameIdDependency,
    decision_input: Hand,
    request: Request,
) -> DopynionResponseCardName:
    log_meta(request, game_id)
    log_hand(decision_input)
    pick = _worst_in_hand(decision_input.hand)
    log_decision(game_id, "TRASH_FROM_HAND", {"chosen": pick})
    return DopynionResponseCardName(game_id=game_id, decision=pick)


@router.post("/confirm_discard_deck")
async def confirm_discard_deck(
    game_id: GameIdDependency,
    request: Request,
) -> DopynionResponseBool:
    log_meta(request, game_id)
    log_decision(game_id, "CONFIRM_DISCARD_DECK")
    return DopynionResponseBool(game_id=game_id, decision=True)


@router.post("/choose_card_to_receive_in_discard")
async def choose_card_to_receive_in_discard(
    game_id: GameIdDependency,
    decision_input: PossibleCards,
    request: Request,
) -> DopynionResponseCardName:
    log_meta(request, game_id)
    log_possible_cards(decision_input)
    pick = _best_from(decision_input.possible_cards)
    log_decision(game_id, "RECEIVE_IN_DISCARD", {"chosen": pick})
    return DopynionResponseCardName(game_id=game_id, decision=pick)


@router.post("/choose_card_to_receive_in_deck")
async def choose_card_to_receive_in_deck(
    game_id: GameIdDependency,
    decision_input: PossibleCards,
    request: Request,
) -> DopynionResponseCardName:
    log_meta(request, game_id)
    log_possible_cards(decision_input)
    pick = _best_from(decision_input.possible_cards)
    log_decision(game_id, "RECEIVE_IN_DECK", {"chosen": pick})
    return DopynionResponseCardName(game_id=game_id, decision=pick)


@router.post("/skip_card_reception_in_hand")
async def skip_card_reception_in_hand(
    game_id: GameIdDependency,
    _decision_input: CardNameAndHand,
    request: Request,
) -> DopynionResponseBool:
    log_meta(request, game_id)
    log_card_name_and_hand(_decision_input)
    log_decision(game_id, "SKIP_RECEPTION_IN_HAND", {"card_name": _decision_input.card_name})
    return DopynionResponseBool(game_id=game_id, decision=True)


@router.post("/trash_money_card_for_better_money_card")
async def trash_money_card_for_better_money_card(
    game_id: GameIdDependency,
    decision_input: MoneyCardsInHand,
    request: Request,
) -> DopynionResponseCardName:
    log_meta(request, game_id)
    log_money_cards(decision_input)
    # if there's a copper, trash it; otherwise pick the lowest-priority money
    money = decision_input.money_in_hand
    pick = "copper" if "copper" in money else sorted(money, key=lambda c: CARD_PRIORITY[c])[0]
    log_decision(game_id, "TRASH_MONEY_FOR_BETTER", {"chosen": pick})
    return DopynionResponseCardName(game_id=game_id, decision=pick)
