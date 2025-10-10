from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from dopynion.data_model import (
    CardNameAndHand,
    Game,
    Hand,
    MoneyCardsInHand,
    PossibleCards,
)
from fastapi import Request


# -----------------------
# JSON / serialization
# -----------------------
def _dump(obj: Any) -> str:
    """Pretty, stable JSON dump for logs."""
    try:
        if hasattr(obj, "model_dump"):
            return json.dumps(obj.model_dump(), ensure_ascii=False, sort_keys=True, indent=2)
        if isinstance(obj, dict | list | tuple):
            return json.dumps(obj, ensure_ascii=False, sort_keys=True, indent=2)
        return json.dumps(obj, ensure_ascii=False, sort_keys=True, indent=2, default=str)
    except Exception:
        # Fallback: last-resort stringification
        return str(obj)


def _as_counts_map(hand: Hand | None) -> dict[str, int]:
    """Return a plain {card: count} dict for a Hand or {}."""
    if hand and getattr(hand, "quantities", None):
        # Ensure plain dict with string keys and int values
        return {str(k): int(v) for k, v in hand.quantities.items()}
    return {}


def _coerce_plain_dict(d: Any) -> dict[str, Any]:
    """Convert defaultdicts/pydantic models/anything mapping-like into a plain dict for logging."""
    if isinstance(d, Mapping):
        return {str(k): _coerce_plain_dict(v) for k, v in d.items()}
    if isinstance(d, list | tuple):
        return [_coerce_plain_dict(v) for v in d]  # type: ignore[list-item]
    return d


def _preview_counts(all_counts: Mapping[str, int]) -> dict[str, int]:
    """Return a stable, curated preview of counts (e.g., stock pile counts)."""
    if not all_counts:
        return {}
    # Focus on relevant Dominion piles used in our bot
    preferred_order = [
        "copper",
        "silver",
        "gold",
        "estate",
        "duchy",
        "province",
        "village",
        "market",
        "laboratory",
        "festival",
        "smithy",
        "woodcutter",
    ]
    preview: dict[str, int] = {}
    for key in preferred_order:
        if key in all_counts:
            preview[key] = int(all_counts[key])
    # Include any other keys not in the preferred list (sorted) as a safety net
    for key in sorted(k for k in all_counts.keys() if k not in preview):
        preview[key] = int(all_counts[key])
    return preview


# -----------------------
# Logging helpers
# -----------------------
def log_meta(request: Request, game_id: str | None) -> None:
    print(
        "[meta]",
        _dump(
            {
                "method": request.method,
                "path": request.url.path,
                "client": getattr(request.client, "host", None),
                "ua": request.headers.get("user-agent"),
                "x-game-id": game_id,
            }
        ),
    )


def log_game(game: Game) -> None:
    """Legacy: full game model (pretty JSON)."""
    print("[body.game]", _dump(game))


def log_game_compact(game: Game) -> None:
    """Concise snapshot of the current game state, suitable for quick scanning."""
    players = []
    for idx, p in enumerate(game.players):
        players.append(
            {
                "idx": idx,
                "name": getattr(p, "name", None),
                "score": getattr(p, "score", 0),
                "hand": _as_counts_map(getattr(p, "hand", None)),
            }
        )

    stock_quantities = getattr(game, "stock", None)
    stock_quantities = getattr(stock_quantities, "quantities", {}) if stock_quantities else {}
    stock_preview = _preview_counts(stock_quantities)

    payload = {
        "finished": bool(getattr(game, "finished", False)),
        "players": players,
        "stock_preview": stock_preview,
    }
    print("[body.game.compact]", _dump(payload))


def log_hand(hand: Hand) -> None:
    print("[body.hand]", _dump(_as_counts_map(hand)))


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


def log_turn_state(game_id: str, state: dict[str, Any]) -> None:
    """Log a one-line summary of our per-turn mutable state."""
    plain_state = _coerce_plain_dict(state)
    # Keep only the most relevant keys if present
    keep = ("coins_left", "buys_left", "bought", "initialized_resources", "counts")
    summary = {k: plain_state.get(k) for k in keep if k in plain_state}
    summary["game_id"] = game_id
    # If counts exists, ensure it's a flat dict with int values
    if isinstance(summary.get("counts"), Mapping):
        summary["counts"] = {str(k): int(v) for k, v in summary["counts"].items()}  # type: ignore[assignment]
    print("[turn_state]", _dump(summary))


def log_context(game_id: str, **kwargs: Any) -> None:
    """Free-form contextual breadcrumbs to help trace decisions."""
    data = {"game_id": game_id}
    data.update(kwargs)
    print("[context]", _dump(data))
