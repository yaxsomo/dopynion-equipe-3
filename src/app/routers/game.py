from __future__ import annotations

from dopynion.data_model import CardNameAndHand, Game, Hand, MoneyCardsInHand, PossibleCards
from fastapi import APIRouter, Request

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
from app.models.responses import (
    DopynionResponseBool,
    DopynionResponseCardName,
    DopynionResponseStr,
    GameIdDependency,
)
from app.strategy.actions import choose_action
from app.strategy.constants import (
    BUY_GOLD_COINS,
    BUY_PROVINCE_COINS,
    BUY_SILVER_COINS,
    COSTS,
    TEAM_NAME,
)
from app.strategy.selector import should_pivot_to_gardens
from app.strategy.state import TURN_STATE, get
from app.strategy.utils import in_stock_state
from app.strategy.strategies import choose_buy_action_for_strategy
from app.strategy.utils import (
    best_from,
    compute_treasure_coins,
    find_me,
    in_stock,
    worst_in_hand,
)

router = APIRouter()


@router.get("/name")
def name() -> str:
    return TEAM_NAME


@router.get("/start_game")
def start_game(game_id: GameIdDependency, request: Request) -> DopynionResponseStr:
    log_meta(request, game_id)
    # NEW: set per-game strategy from header (defaults to "baseline")
    state = get_state(game_id)
    chosen = request.headers.get("X-Strategy", "baseline").strip().lower()
    state["strategy"] = chosen
    return DopynionResponseStr(game_id=game_id, decision="OK")


@router.get("/start_turn")
def start_turn(game_id: GameIdDependency, request: Request) -> DopynionResponseStr:
    log_meta(request, game_id)
    state = get_state(game_id)
    state["bought"] = False
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


@router.post("/play")
def play(game: Game, game_id: GameIdDependency, request: Request) -> DopynionResponseStr:
    log_meta(request, game_id)
    log_game_compact(game)
    if not getattr(game, "players", None) or len(game.players) == 0:
        decision = "END_TURN"
        log_decision(game_id, decision)
        return DopynionResponseStr(game_id=game_id, decision=decision)

    me_idx = find_me(game)
    if me_idx is None or me_idx < 0 or me_idx >= len(game.players):
        decision = "END_TURN"
        log_decision(game_id, decision)
        return DopynionResponseStr(game_id=game_id, decision=decision)

    # --- Normal flow ---
    state = get_state(game_id)

    # Ensure per-turn defaults
    state.setdefault("phase", "ACTION")
    state.setdefault("actions_left", 1)
    state.setdefault("action_coins", 0)
    state.setdefault("extra_buys", 0)
    state.setdefault("buys_left", 1)

    # Initialize long-term plan flags once
    if "gardens_plan" not in state:
        state["gardens_plan"] = should_pivot_to_gardens(game, me_idx)

    log_turn_state(game_id, state)

    # ACTION phase
    if state.get("phase") == "ACTION":
        action_decision = choose_action(game, me_idx, state)
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
        state["phase"] = "BUY"

    # BUY phase
    treasure_coins = compute_treasure_coins(game, me_idx)
    coins_left = treasure_coins + int(state.get("action_coins", 0))
    buys_left = int(state.get("buys_left", 1)) + int(state.get("extra_buys", 0))
    state["coins_left"] = coins_left

    # Base affordability by real thresholds
    affordable_any = (
        (game.stock.quantities.get("province", 0) > 0 and coins_left >= BUY_PROVINCE_COINS)
        or (game.stock.quantities.get("gold", 0) > 0 and coins_left >= BUY_GOLD_COINS)
        or coins_left >= BUY_SILVER_COINS
    )

    # If not affordable yet: allow a copper *only* when on Gardens AND we have spare buys
    # (so the copper won't replace a better buy). This matches the pipeline fallback.
    if not affordable_any and state.get("gardens_plan", False) and in_stock(game, "copper"):
        extra_buys = int(state.get("extra_buys", 0))
        if extra_buys > 0 or buys_left > 1:
            affordable_any = True

    if buys_left <= 0 or not affordable_any:
        decision = "END_TURN"
        log_decision(game_id, decision)
        return DopynionResponseStr(game_id=game_id, decision=decision)

    # Choose buy according to the active strategy (set in /start_game via X-Strategy)
    strategy_key = str(state.get("strategy", "baseline"))
    decision = choose_buy_action_for_strategy(strategy_key, game, coins_left, me_idx, state)
    log_context(
        game_id,
        phase="buy",
        me_idx=me_idx,
        coins_left=coins_left,
        buys_left=buys_left,
        chosen=decision,
        gardens_plan=state.get("gardens_plan", False),
    )

    
    # ---- FINAL LEGALITY GUARD: never send an unaffordable or out-of-stock BUY ----
    if decision.startswith("BUY"):
        try:
            _, _card = decision.split(" ", 1)
            _card = _card.strip().lower()
            _cost = COSTS.get(_card, 99)
            _stock_ok = in_stock(game, _card)
            _buys_ok = buys_left > 0
            _coins_ok = coins_left >= _cost
            if not (_buys_ok and _coins_ok and _stock_ok):
                def _affordable_fallback() -> str:
                    if coins_left >= BUY_PROVINCE_COINS and in_stock(game, "province"):
                        return "BUY province"
                    if coins_left >= BUY_GOLD_COINS and in_stock(game, "gold"):
                        return "BUY gold"
                    if coins_left >= BUY_SILVER_COINS and in_stock(game, "silver"):
                        return "BUY silver"
                    for _c in ("market", "festival", "laboratory", "village", "smithy", "woodcutter"):
                        if in_stock(game, _c) and COSTS.get(_c, 99) <= coins_left:
                            return f"BUY {_c}"
                    if state.get("gardens_plan", False) and in_stock(game, "copper"):
                        extra_buys = int(state.get("extra_buys", 0))
                        if extra_buys > 0 or buys_left > 1:
                            return "BUY copper"
                    return "END_TURN"
                decision = _affordable_fallback()
        except Exception:
            decision = "END_TURN"
    if decision.startswith("BUY"):
            state["bought"] = True
            try:
                _, card = decision.split(" ", 1)
                card = card.strip().lower()
                cost = COSTS.get(card, 0)
                state["coins_left"] = max(0, coins_left - cost)
                state["buys_left"] = max(0, int(state.get("buys_left", 1)) - 1)
                counts = state["counts"]  # type: ignore[assignment]
                counts[card] += 1
            except Exception:
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
    game_id: GameIdDependency, decision_input: CardNameAndHand, request: Request
) -> DopynionResponseBool:
    log_meta(request, game_id)
    log_card_name_and_hand(decision_input)
    log_decision(game_id, "CONFIRM_DISCARD", {"card_name": decision_input.card_name})
    return DopynionResponseBool(game_id=game_id, decision=True)


@router.post("/discard_card_from_hand")
async def discard_card_from_hand(
    game_id: GameIdDependency, decision_input: Hand, request: Request
) -> DopynionResponseCardName:
    log_meta(request, game_id)
    log_hand(decision_input)

    # Fuzz-safe: empty / missing hand -> pick a harmless default
    cards = getattr(decision_input, "hand", None) or []
    if not cards:
        pick: str = "copper"
    else:
        pick = worst_in_hand(cards)

    log_decision(game_id, "DISCARD_FROM_HAND", {"chosen": pick})
    return DopynionResponseCardName(game_id=game_id, decision=pick)


@router.post("/confirm_trash_card_from_hand")
async def confirm_trash_card_from_hand(
    game_id: GameIdDependency, decision_input: CardNameAndHand, request: Request
) -> DopynionResponseBool:
    log_meta(request, game_id)
    log_card_name_and_hand(decision_input)
    log_decision(game_id, "CONFIRM_TRASH", {"card_name": decision_input.card_name})
    return DopynionResponseBool(game_id=game_id, decision=True)


@router.post("/trash_card_from_hand")
async def trash_card_from_hand(
    game_id: GameIdDependency, decision_input: Hand, request: Request
) -> DopynionResponseCardName:
    log_meta(request, game_id)
    log_hand(decision_input)

    # Fuzz-safe: empty / missing hand -> pick a harmless default
    cards = getattr(decision_input, "hand", None) or []
    if not cards:
        pick: str = "copper"
    else:
        pick = worst_in_hand(cards)

    log_decision(game_id, "TRASH_FROM_HAND", {"chosen": pick})
    return DopynionResponseCardName(game_id=game_id, decision=pick)


@router.post("/confirm_discard_deck")
async def confirm_discard_deck(game_id: GameIdDependency, request: Request) -> DopynionResponseBool:
    log_meta(request, game_id)
    log_decision(game_id, "CONFIRM_DISCARD_DECK")
    return DopynionResponseBool(game_id=game_id, decision=True)


@router.post("/choose_card_to_receive_in_discard")
async def choose_card_to_receive_in_discard(
    game_id: GameIdDependency, decision_input: PossibleCards, request: Request
) -> DopynionResponseCardName:
    log_meta(request, game_id)
    log_possible_cards(decision_input)

    options = list(getattr(decision_input, "possible_cards", None) or [])
    if not options:
        pick: str = "copper"
    else:
        pick = best_from(options)

    log_decision(game_id, "RECEIVE_IN_DISCARD", {"chosen": pick})
    return DopynionResponseCardName(game_id=game_id, decision=pick)


@router.post("/choose_card_to_receive_in_deck")
async def choose_card_to_receive_in_deck(
    game_id: GameIdDependency, decision_input: PossibleCards, request: Request
) -> DopynionResponseCardName:
    log_meta(request, game_id)
    log_possible_cards(decision_input)

    options = list(getattr(decision_input, "possible_cards", None) or [])
    if not options:
        pick: str = "copper"
    else:
        pick = best_from(options)

    log_decision(game_id, "RECEIVE_IN_DECK", {"chosen": pick})
    return DopynionResponseCardName(game_id=game_id, decision=pick)


@router.post("/skip_card_reception_in_hand")
async def skip_card_reception_in_hand(
    game_id: GameIdDependency, decision_input: CardNameAndHand, request: Request
) -> DopynionResponseBool:
    log_meta(request, game_id)
    log_card_name_and_hand(decision_input)
    log_decision(game_id, "SKIP_RECEPTION_IN_HAND", {"card_name": decision_input.card_name})
    return DopynionResponseBool(game_id=game_id, decision=True)


@router.post("/trash_money_card_for_better_money_card")
async def trash_money_card_for_better_money_card(
    game_id: GameIdDependency, decision_input: MoneyCardsInHand, request: Request
) -> DopynionResponseCardName:
    log_meta(request, game_id)
    log_money_cards(decision_input)

    money = list(getattr(decision_input, "money_in_hand", []) or [])

    # If fuzzing gives us no money cards, pick a safe default
    if not money:
        pick: str = "copper"
    else:
        # Prefer to trash copper if present; otherwise trash the lowest “value” card
        pick = "copper" if "copper" in money else sorted(money)[0]

    log_decision(game_id, "TRASH_MONEY_FOR_BETTER", {"chosen": pick})
    return DopynionResponseCardName(game_id=game_id, decision=pick)
