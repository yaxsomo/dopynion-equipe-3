from __future__ import annotations

from dopynion.data_model import CardName, Game

from .constants import (
    CARD_PRIORITY,
    TEAM_NAME,
    TERMINAL_ACTIONS,
)


def in_stock(game: Game, card: str) -> bool:
    return (game.stock.quantities or {}).get(card, 0) > 0


def score_status(game: Game, me_idx: int) -> tuple[int, int]:
    my_score = getattr(game.players[me_idx], "score", 0) or 0
    opp = [getattr(p, "score", 0) or 0 for i, p in enumerate(game.players) if i != me_idx]
    return my_score, (max(opp) if opp else 0)


def safe_get_me(game: Game, me_idx: int):
    """Return player at index or None if out-of-range / missing."""
    players = getattr(game, "players", None) or []
    if me_idx is None or me_idx < 0 or me_idx >= len(players):
        return None
    return players[me_idx]


def compute_treasure_coins(game: Game, me_idx: int) -> int:
    """Return coins from treasure cards currently in hand (no action bonuses)."""
    me = safe_get_me(game, me_idx)
    if not me or not getattr(me, "hand", None):
        return 0
    q = (me.hand.quantities or {}) or {}
    return q.get("copper", 0) * 1 + q.get("silver", 0) * 2 + q.get("gold", 0) * 3


def terminal_capacity(counts: dict[str, int]) -> int:
    terminals = sum(counts.get(t, 0) for t in TERMINAL_ACTIONS)
    plus_actions = (
        counts.get("village", 0) * 2
        + counts.get("market", 0) * 1
        + counts.get("festival", 0) * 2
        + counts.get("laboratory", 0) * 1
    )
    return 1 + plus_actions - terminals


def find_me(game: Game) -> int:
    players = getattr(game, "players", None) or []
    if not players:
        return -1
    # name-based
    for i, p in enumerate(players):
        if getattr(p, "name", None) and TEAM_NAME in p.name:
            return i
    with_hand = [i for i, p in enumerate(players) if getattr(p, "hand", None)]
    if len(with_hand) == 1:
        return with_hand[0]
    return 0  # safe default when players exist


def best_from(options: list[CardName]) -> CardName:
    return sorted(options, key=lambda c: (-CARD_PRIORITY[c], c))[0]


def worst_in_hand(hand: list[CardName]) -> CardName:
    def score(c: CardName) -> tuple[int, int]:
        if c in {"estate", "curse"}:
            return (0, CARD_PRIORITY[c])
        if c == "copper":
            return (1, CARD_PRIORITY[c])
        return (2, CARD_PRIORITY[c])

    return sorted(hand, key=lambda c: score(c))[0]
