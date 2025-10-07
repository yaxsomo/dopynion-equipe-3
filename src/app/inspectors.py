from __future__ import annotations

import json
from typing import Any

from dopynion.data_model import (
    CardNameAndHand,
    Game,
    Hand,
    MoneyCardsInHand,
    PossibleCards,
)
from fastapi import Request


def _dump(obj: Any) -> str:
    try:
        if hasattr(obj, "model_dump"):
            return json.dumps(obj.model_dump(), ensure_ascii=False)
        return json.dumps(obj, ensure_ascii=False, default=str)
    except Exception:
        return str(obj)


def log_meta(request: Request, game_id: str | None) -> None:
    print(
        "[meta]",
        f"method={request.method}",
        f"path={request.url.path}",
        f"client={getattr(request.client, 'host', None)}",
        f"ua={request.headers.get('user-agent')!r}",
        f"x-game-id={game_id!r}",
    )


def log_game(game: Game) -> None:
    print("[body.game]", _dump(game))


def log_hand(hand: Hand) -> None:
    print("[body.hand]", _dump(hand))


def log_card_name_and_hand(payload: CardNameAndHand) -> None:
    print("[body.card_name_and_hand]", _dump(payload))


def log_possible_cards(payload: PossibleCards) -> None:
    preview = payload.possible_cards[:5]
    print(
        "[body.possible_cards]", _dump({"count": len(payload.possible_cards), "preview": preview})
    )


def log_money_cards(payload: MoneyCardsInHand) -> None:
    print("[body.money_in_hand]", _dump(payload))


def log_decision(game_id: str, decision: str, extra: dict[str, Any] | None = None) -> None:
    data: dict[str, Any] = {"game_id": game_id, "decision": decision}
    if extra:
        data.update(extra)
    print("[decision]", _dump(data))
