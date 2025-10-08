from __future__ import annotations

from collections import defaultdict
from typing import Annotated

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
    log_decision,
    log_game,
    log_hand,
    log_meta,
    log_money_cards,
    log_possible_cards,
)

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
MAX_LABS = 3
MAX_SMITHIES = 2

# --- costs and per-action bonuses (per client rules) ---
COSTS: dict[str, int] = {
    "province": 8,
    "duchy": 5,
    "estate": 2,
    "gold": 6,
    "silver": 3,
    "copper": 0,
    "laboratory": 5,
    "market": 5,
    "smithy": 4,
    "village": 3,
    "woodcutter": 3,
    "festival": 5,
}

# Bonus coins granted by *playing* these actions during the turn
ACTION_COIN_BONUS: dict[str, int] = {
    "laboratory": 2,  # client says Labo: +2 coins, +1 card
    "market": 1,  # Market: +1 coin, +1 buy, +1 card
    "festival": 2,  # Festival: +2 coins, +1 buy
    # smithy/village/woodcutter give 0 coins per the client's description
}

# Extra buys granted by *playing* these actions during the turn
ACTION_BUY_BONUS: dict[str, int] = {
    "market": 1,
    "woodcutter": 1,
    "festival": 1,
}


def _compute_turn_resources(game: Game, me_idx: int) -> tuple[int, int]:
    """Estimate (coins_total, buys_total) for the current turn from treasures + action bonuses.

    We assume actions that give +coins/+buys can be played before buying.
    """
    me = game.players[me_idx]
    q = (me.hand.quantities if me.hand else {}) or {}

    coins = q.get("copper", 0) * 1 + q.get("silver", 0) * 2 + q.get("gold", 0) * 3

    # add action coin bonuses (per quantity of those action cards in hand)
    for card, bonus in ACTION_COIN_BONUS.items():
        coins += q.get(card, 0) * bonus

    buys = 1  # base buy
    for card, bonus in ACTION_BUY_BONUS.items():
        buys += q.get(card, 0) * bonus

    return coins, buys


FIVE_COST_PREFER = ["laboratory", "market", "festival"]
FOUR_COST_PREFER = ["smithy", "village"]
# crude priority table (higher is better)
CARD_PRIORITY = defaultdict(
    lambda: 0,
    {
        "province": 100,
        "gold": 80,
        "laboratory": 70,
        "market": 60,
        "smithy": 55,
        "festival": 50,
        "village": 40,
        "silver": 30,
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
    log_decision(game_id, "OK")
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


def _endgame_buy(
    _game: Game, coins: int, provinces_left: int, my_score: int, best_opp: int
) -> str | None:
    """Heuristics when piles are low."""
    if provinces_left <= ENDGAME_PROVINCE_THRESHOLD:
        if coins >= BUY_PROVINCE_COINS and _game.stock.quantities.get("province", 0) > 0:
            return "BUY province"
        if coins >= BUY_5_COST_COINS and _game.stock.quantities.get("duchy", 0) > 0:
            return "BUY duchy"
        if (
            coins >= BUY_SILVER_COINS
            and my_score >= best_opp
            and _game.stock.quantities.get("estate", 0) > 0
        ):
            return "BUY estate"
    return None


def _midgame_buy(
    _game: Game, coins: int, provinces_left: int, my_score: int, best_opp: int
) -> str | None:
    """Greening pressure before the final two provinces."""
    if provinces_left <= MIDGAME_PROVINCE_THRESHOLD:
        if coins >= BUY_PROVINCE_COINS and _game.stock.quantities.get("province", 0) > 0:
            return "BUY province"
        if (
            coins >= BUY_5_COST_COINS
            and _game.stock.quantities.get("duchy", 0) > 0
            and my_score <= best_opp
        ):
            return "BUY duchy"
    return None


def _economy_buy(_game: Game, coins: int) -> str | None:
    """Gold when we can afford it and provinces aren't forced."""
    if coins >= BUY_GOLD_COINS and _game.stock.quantities.get("gold", 0) > 0:
        return "BUY gold"
    return None


def _five_cost_buy(_game: Game, coins: int, counts: dict[str, int]) -> str | None:
    decision: str | None = None

    # Only consider if we have enough coins
    if coins >= BUY_5_COST_COINS:
        # Prefer a few labs first
        if (
            _game.stock.quantities.get("laboratory", 0) > 0
            and counts.get("laboratory", 0) < MAX_LABS
        ):
            decision = "BUY laboratory"
        else:
            # If terminals are colliding, prefer action sources
            if _terminal_capacity(counts) <= 0:
                if _game.stock.quantities.get("market", 0) > 0:
                    decision = "BUY market"
                elif _game.stock.quantities.get("village", 0) > 0 and coins >= BUY_4_COST_COINS:
                    decision = "BUY village"

            # Otherwise take best available from preferred set
            if decision is None:
                for c in FIVE_COST_PREFER:
                    if _game.stock.quantities.get(c, 0) > 0:
                        decision = f"BUY {c}"
                        break

            # Fallback
            if decision is None and _game.stock.quantities.get("silver", 0) > 0:
                decision = "BUY silver"

    return decision


def _four_cost_buy(_game: Game, coins: int, counts: dict[str, int]) -> str | None:
    if coins < BUY_4_COST_COINS:
        return None
    if _terminal_capacity(counts) <= 0 and _game.stock.quantities.get("village", 0) > 0:
        return "BUY village"
    if (
        _game.stock.quantities.get("smithy", 0) > 0
        and counts.get("smithy", 0) < MAX_SMITHIES
        and _terminal_capacity(counts) > 0
    ):
        return "BUY smithy"
    if _game.stock.quantities.get("village", 0) > 0:
        return "BUY village"
    if _game.stock.quantities.get("silver", 0) > 0:
        return "BUY silver"
    return None


def _three_cost_buy(_game: Game, coins: int) -> str | None:
    if coins >= BUY_SILVER_COINS and _game.stock.quantities.get("silver", 0) > 0:
        return "BUY silver"
    return None


def choose_buy_action(_game: Game, coins: int, me_idx: int, state: dict[str, object]) -> str:
    counts: defaultdict[str, int] = state["counts"]  # type: ignore[assignment]
    provinces_left = _game.stock.quantities.get("province", 0)
    my_score, best_opp = _score_status(_game, me_idx)

    # Order of checks from most forcing to least
    decision = None  # type: Optional[str]

    # Province, greening pressure
    if coins >= BUY_PROVINCE_COINS and _game.stock.quantities.get("province", 0) > 0:
        decision = "BUY province"

    if decision is None:
        decision = _endgame_buy(_game, coins, provinces_left, my_score, best_opp)
    if decision is None:
        decision = _midgame_buy(_game, coins, provinces_left, my_score, best_opp)
    if decision is None:
        decision = _economy_buy(_game, coins)
    if decision is None:
        decision = _five_cost_buy(_game, coins, counts)
    if decision is None:
        decision = _four_cost_buy(_game, coins, counts)
    if decision is None:
        decision = _three_cost_buy(_game, coins)

    return decision or "END_TURN"


@router.post("/play")
def play(_game: Game, game_id: GameIdDependency, request: Request) -> DopynionResponseStr:
    log_meta(request, game_id)
    log_game(_game)

    state = _get_state(game_id)

    me_idx = _find_me(_game)

    # Initialize per-turn resources on first /play call of the turn
    if not state.get("bought") and not state.get("initialized_resources"):
        coins_total, buys_total = _compute_turn_resources(_game, me_idx)
        state["coins_left"] = coins_total
        state["buys_left"] = buys_total
        state["initialized_resources"] = True  # mark so we don't recompute mid-turn

    # Fallback if keys are missing (robustness)
    coins_left = int(state.get("coins_left", 0))  # type: ignore[arg-type]
    buys_left = int(state.get("buys_left", 1))  # type: ignore[arg-type]

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

    # Mark and update state after a buy
    if decision.startswith("BUY"):
        state["bought"] = True
        try:
            _, card = decision.split(" ", 1)
            card = card.strip().lower()
            cost = COSTS.get(card, 0)
            state["coins_left"] = max(0, coins_left - cost)
            state["buys_left"] = max(0, buys_left - 1)

            counts: defaultdict[str, int] = state["counts"]  # type: ignore[assignment]
            counts[card] += 1
        except Exception:
            # keep state consistent even on parsing issues
            state["coins_left"] = coins_left
            state["buys_left"] = max(0, buys_left - 1)

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
