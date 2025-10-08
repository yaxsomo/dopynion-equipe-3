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
TURN_STATE: dict[str, dict[str, bool]] = defaultdict(lambda: {"bought": False})
router = APIRouter()
# ----- buying thresholds (avoid magic numbers) -----
BUY_PROVINCE_COINS = 8
BUY_GOLD_COINS = 6
BUY_5_COST_COINS = 5
BUY_4_COST_COINS = 4
BUY_SILVER_COINS = 3

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
    TURN_STATE[game_id]["bought"] = False  # <-- reset per turn
    log_decision(game_id, "OK")
    return DopynionResponseStr(game_id=game_id, decision="OK")


def choose_buy_action(_game: Game, coins: int) -> str:
    """Return the best BUY decision based on current coins and stock."""
    decision = "END_TURN"

    if coins >= BUY_PROVINCE_COINS and _game.stock.quantities.get("province", 0) > 0:
        decision = "BUY province"
    elif coins >= BUY_GOLD_COINS and _game.stock.quantities.get("gold", 0) > 0:
        decision = "BUY gold"
    elif coins >= BUY_5_COST_COINS:
        for c in FIVE_COST_PREFER:
            if _game.stock.quantities.get(c, 0) > 0:
                decision = f"BUY {c}"
                break
        else:
            decision = "BUY silver"
    elif coins >= BUY_4_COST_COINS:
        for c in FOUR_COST_PREFER:
            if _game.stock.quantities.get(c, 0) > 0:
                decision = f"BUY {c}"
                break
        else:
            decision = "BUY silver"
    elif coins >= BUY_SILVER_COINS and _game.stock.quantities.get("silver", 0) > 0:
        decision = "BUY silver"

    return decision


@router.post("/play")
def play(_game: Game, game_id: GameIdDependency, request: Request) -> DopynionResponseStr:
    log_meta(request, game_id)
    log_game(_game)

    # Stop if we already bought this turn
    if TURN_STATE[game_id]["bought"]:
        decision = "END_TURN"
        log_decision(game_id, decision)
        return DopynionResponseStr(game_id=game_id, decision=decision)

    me = _game.players[1]  # we are usually index 1
    q = (me.hand.quantities if me.hand else {}) or {}
    coins = q.get("copper", 0) * 1 + q.get("silver", 0) * 2 + q.get("gold", 0) * 3

    # Delegated decision logic
    decision = choose_buy_action(_game, coins)

    # Mark buy done if needed
    if decision.startswith("BUY"):
        TURN_STATE[game_id]["bought"] = True

    log_decision(game_id, decision)
    return DopynionResponseStr(game_id=game_id, decision=decision)


@router.get("/end_game")
def end_game(game_id: GameIdDependency, request: Request) -> DopynionResponseStr:
    log_meta(request, game_id)
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
