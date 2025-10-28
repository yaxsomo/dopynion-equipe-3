from __future__ import annotations

"""
Unified utilities for the Dominion bot.

Exports (so your imports won't break again):
- Stock / supply:    in_stock, in_stock_state, best_from
- Player access:     safe_get_me, find_me, find_me_idx
- Scoring / engine:  score_status, terminal_capacity
- Coins:             compute_treasure_coins, compute_total_coins
- Hand helpers:      hand_counts, worst_in_hand   (robust to many input shapes)

All functions are defensive: they accept object- or dict-shaped game payloads.
"""

from typing import Any, Iterable, Optional, Tuple, Dict, List

# -----------------------------------------------------------------------------
# Low-level helpers (introspect game/state shapes)
# -----------------------------------------------------------------------------

def _get_attr_or_key(obj: Any, *names: str):
    """Return the first attribute/key found among names, else None."""
    for n in names:
        if hasattr(obj, n):
            return getattr(obj, n)
    if isinstance(obj, dict):
        for n in names:
            if n in obj:
                return obj[n]
    return None


def _extract_players(obj: Any) -> List[Any]:
    """Return a players list from common shapes or [] if not found."""
    try:
        for name in ("players", "players_info", "playersInfos", "seats"):
            pl = getattr(obj, name, None)
            if isinstance(pl, (list, tuple)):
                return list(pl)
        if isinstance(obj, dict):
            for name in ("players", "players_info", "playersInfos", "seats"):
                pl = obj.get(name)
                if isinstance(pl, (list, tuple)):
                    return list(pl)
    except Exception:
        pass
    return []


def _extract_stock(obj: Any) -> dict:
    """
    Try to get a {card_name: qty} mapping from different shapes:
    - Game-like: game.stock.quantities
    - state dict: state["game"].stock.quantities
    - dict that already looks like quantities
    """
    try:
        stock = getattr(getattr(obj, "stock", None), "quantities", None)
        if isinstance(stock, dict):
            return stock
        if isinstance(obj, dict):
            game = obj.get("game")
            if game is not None:
                stock = getattr(getattr(game, "stock", None), "quantities", None)
                if isinstance(stock, dict):
                    return stock
            maybe = obj.get("stock", obj)
            if isinstance(maybe, dict):
                return maybe
    except Exception:
        pass
    return {}


def _extract_player_hand(game_or_state: Any, me_idx: Any) -> Any:
    """Return a 'hand' object from a Game-like or state dict."""
    me = safe_get_me(game_or_state, me_idx)
    if me is not None:
        h = getattr(me, "hand", None) or (me.get("hand") if isinstance(me, dict) else None)
        if h is not None:
            return h

    # Try game.me.hand if me_idx lookup failed
    try:
        me_obj = getattr(game_or_state, "me", None)
        if me_obj is not None:
            h = getattr(me_obj, "hand", None)
            if h is not None:
                return h
    except Exception:
        pass

    # Try state dict path: state["game"]["players"][me_idx]["hand"]
    if isinstance(game_or_state, dict):
        g = game_or_state.get("game")
        if g is not None:
            try:
                players = getattr(g, "players", None) or getattr(g, "players_info", None) or getattr(g, "playersInfos", None)
                if players and 0 <= int(me_idx) < len(players):
                    h = getattr(players[int(me_idx)], "hand", None)
                    if h is not None:
                        return h
            except Exception:
                pass

    return None


def _to_quantities_from_hand(hand_obj: Any) -> Dict[str, int]:
    """
    Normalize a 'hand' into {card_name_lower: count}.
    Supports:
      - hand.quantities (dict)
      - hand as a list/tuple of card names
      - hand as a dict {card_name: count}
    """
    qty = getattr(hand_obj, "quantities", None)
    if isinstance(qty, dict):
        return {str(k).lower(): int(v) for k, v in qty.items()}

    if isinstance(hand_obj, (list, tuple)):
        out: Dict[str, int] = {}
        for x in hand_obj:
            k = str(x).lower()
            out[k] = out.get(k, 0) + 1
        return out

    if isinstance(hand_obj, dict):
        return {str(k).lower(): int(v) for k, v in hand_obj.items()}

    return {}

# -----------------------------------------------------------------------------
# Public: stock / supply
# -----------------------------------------------------------------------------

def in_stock(game_or_state: Any, card: str) -> bool:
    """True if the supply pile for `card` has > 0 copies remaining."""
    stock = _extract_stock(game_or_state)
    return int(stock.get(card.lower(), 0)) > 0


def in_stock_state(game_or_state: Any, card: str) -> bool:  # alias
    return in_stock(game_or_state, card)


def best_from(game_or_state: Any, candidates: Iterable[str]) -> Optional[str]:
    """Return the first in-stock card among candidates, else None."""
    for c in candidates:
        if in_stock(game_or_state, c):
            return c
    return None

# -----------------------------------------------------------------------------
# Public: player access
# -----------------------------------------------------------------------------

def safe_get_me(game: Any, me_idx: Any) -> Optional[Any]:
    """
    Best-effort retrieval of 'my' player object from a Game or game-like dict.
    """
    if game is None:
        return None

    me_field = _get_attr_or_key(game, "me")
    if me_field is not None and not isinstance(me_field, (int, float)):
        return me_field  # already a player object

    players = _get_attr_or_key(game, "players", "players_info", "playersInfos")
    if isinstance(players, (list, tuple)):
        # game.me is an index?
        if isinstance(me_field, (int, float)):
            mi = int(me_field)
            if 0 <= mi < len(players):
                return players[mi]
        # me_idx provided?
        try:
            idx = int(me_idx)
            if 0 <= idx < len(players):
                return players[idx]
        except Exception:
            pass
        # Flag-based fallback
        for p in players:
            if getattr(p, "is_me", False) or getattr(p, "me", False):
                return p
    return None


def find_me(game: Any, me_idx: Any = None) -> Tuple[Optional[Any], Optional[int]]:
    """
    Return (my_player_obj, my_index) best-effort. Robust to various shapes.
    """
    players = _extract_players(game)

    # 1) game.me is a player object?
    try:
        me_field = getattr(game, "me", None)
    except Exception:
        me_field = None
    if me_field is not None and not isinstance(me_field, (int, float)):
        me_obj = me_field
        idx = None
        for i, p in enumerate(players):
            if p is me_obj or p == me_obj:
                idx = i
                break
        return me_obj, idx

    # 2) game.me is an index?
    if isinstance(me_field, (int, float)):
        i = int(me_field)
        if 0 <= i < len(players):
            return players[i], i
        return None, i

    # 3) explicit me_idx
    try:
        if me_idx is not None:
            i = int(me_idx)
            if 0 <= i < len(players):
                return players[i], i
            return None, i
    except Exception:
        pass

    # 4) scan for flags
    for i, p in enumerate(players):
        try:
            if getattr(p, "is_me", False) or getattr(p, "me", False):
                return p, i
            if isinstance(p, dict) and (p.get("is_me") or p.get("me")):
                return p, i
        except Exception:
            continue

    return None, None


def find_me_idx(game: Any, me_idx: Any = None) -> Optional[int]:
    """Return my index only."""
    _, idx = find_me(game, me_idx)
    return idx

# -----------------------------------------------------------------------------
# Public: scoring / capacity
# -----------------------------------------------------------------------------

def _player_score(p: Any) -> int:
    """Best-effort extraction of a player's score."""
    for name in ("score", "victory_points", "victoryPoints", "vp", "points"):
        try:
            v = getattr(p, name, None)
            if v is None and isinstance(p, dict):
                v = p.get(name)
            if v is not None:
                return int(v)
        except Exception:
            continue
    return 0


def score_status(game: Any, me_idx: Any) -> Tuple[int, int]:
    """
    Returns (my_score, best_opponent_score). Robust to different Game shapes.
    """
    me = safe_get_me(game, me_idx)
    my_score = _player_score(me) if me is not None else 0

    players = _get_attr_or_key(game, "players", "players_info", "playersInfos")
    best_opp = 0
    if isinstance(players, (list, tuple)):
        for p in players:
            if p is me:
                continue
            best_opp = max(best_opp, _player_score(p))
    return my_score, best_opp


def terminal_capacity(counts: Dict[str, int]) -> int:
    """
    Heuristic 'action capacity' of the deck:
    +Actions producers (approx) minus number of terminal action cards.
    Positive => you can add more terminals safely.
    """
    c = {k: int(v) for k, v in (counts or {}).items()}

    # +Actions producers (common base/near-base cards)
    plus_actions = (
        2 * c.get("village", 0) +
        1 * c.get("market", 0) +
        1 * c.get("laboratory", 0) +
        2 * c.get("festival", 0) +
        2 * c.get("port", 0) +
        1 * c.get("poacher", 0) +
        1 * c.get("cellar", 0) +
        2 * c.get("farmingvillage", 0) +
        1 * c.get("magpie", 0)
    )

    # Terminals we commonly buy
    terminals = (
        c.get("smithy", 0) +
        c.get("witch", 0) +
        c.get("militia", 0) +
        c.get("bandit", 0) +
        c.get("bureaucrat", 0) +
        c.get("chancellor", 0) +
        c.get("woodcutter", 0) +
        c.get("moneylender", 0) +
        c.get("remodel", 0) +
        c.get("remake", 0) +
        c.get("mine", 0) +
        c.get("feast", 0) +
        c.get("workshop", 0)
    )

    return plus_actions - terminals

# -----------------------------------------------------------------------------
# Public: coins
# -----------------------------------------------------------------------------

_TREASURE_VALUES: Dict[str, int] = {
    "copper": 1,
    "silver": 2,
    "gold": 3,
    # add "platinum": 5 if you ever use it
}

def compute_treasure_coins(game_or_state: Any, me_idx: Any) -> int:
    """
    Sum coin value of treasures currently in hand (Copper/Silver/Gold...).
    Does NOT include +$ from actions; see compute_total_coins for that.
    """
    hand = _extract_player_hand(game_or_state, me_idx)
    q = _to_quantities_from_hand(hand) if hand is not None else {}
    total = 0
    for name, cnt in q.items():
        total += _TREASURE_VALUES.get(name, 0) * int(cnt)
    return total


def compute_total_coins(game_or_state: Any, me_idx: Any, state: Any = None) -> int:
    """Treasures in hand + action coins from state (if provided)."""
    base = compute_treasure_coins(game_or_state, me_idx)
    bonus = 0
    if isinstance(state, dict):
        try:
            bonus = int(state.get("action_coins", 0))
        except Exception:
            bonus = 0
    return base + bonus

# -----------------------------------------------------------------------------
# Public: hand helpers
# -----------------------------------------------------------------------------

def hand_counts(game_or_state: Any = None, me_idx: Any = None, hand_obj: Any = None) -> Dict[str, int]:
    """
    Return current hand as {card: count} (lowercased).
    You can pass either (game_or_state, me_idx) or a raw hand_obj.
    """
    if hand_obj is None:
        hand_obj = _extract_player_hand(game_or_state, me_idx)
    return _to_quantities_from_hand(hand_obj) if hand_obj is not None else {}


def worst_in_hand(source: Any = None, me_idx: Any = None, policy: str = "trash") -> Optional[str]:
    """
    Pick the 'worst' card in hand according to a simple policy, for use by
    trashers (e.g., Chapel/Remake), Remodel targets, or discards.

    Accepts either:
      - source = game_or_state (with me_idx), OR
      - source = dict hand-counts (already {card: count})
    Returns a single card name (str) or None if hand empty.

    Policies:
      - "trash"   : prioritize junk (curse > estate > copper > weak terminals)
      - "remodel" : similar to trash but avoids 'curse' if remodel needs cost+2
      - "discard" : prefers low-impact cards to pitch
    """
    # Get hand counts
    if isinstance(source, dict) and (me_idx is None or not source):
        q = {str(k).lower(): int(v) for k, v in source.items()}
    else:
        q = hand_counts(source, me_idx)

    if not q:
        return None

    # Scoring tables (lower score = worse / higher priority to remove)
    base = {
        "curse": -100,
        "estate": -50,
        "copper": -40,
        # weak terminals / filler
        "chancellor": -20,
        "woodcutter": -18,
        "bureaucrat": -16,
        "poacher": -14,
        "militia": -12,
        "silver": -10,
        # neutral / engine parts (higher -> keep)
        "cellar": 0,
        "village": 5,
        "smithy": 6,
        "market": 8,
        "laboratory": 10,
        "festival": 10,
        "gold": 12,
        "province": 50,
        "duchy": 30,
        "estate_vp": 5,  # alias if some engines rename it
    }

    # Adjust by policy
    score = dict(base)
    if policy == "remodel":
        # If your Remodel expects gain-by-cost, curse may be useless -> slightly less priority
        score["curse"] = -30
    elif policy == "discard":
        # Discard is softer; prefer pitching copper/estate/weak terminals
        for k in ("curse", "estate", "copper", "chancellor", "woodcutter", "bureaucrat", "poacher", "militia"):
            score[k] = score.get(k, -10) - 5

    # Pick the card with the lowest score that's actually in hand
    candidate = None
    best_val = 10**9
    for name, cnt in q.items():
        if cnt <= 0:
            continue
        val = score.get(name, 0)
        if val < best_val:
            best_val = val
            candidate = name

    return candidate

# -----------------------------------------------------------------------------
# __all__ — make these names importable everywhere
# -----------------------------------------------------------------------------

__all__ = [
    # stock
    "in_stock", "in_stock_state", "best_from",
    # players
    "safe_get_me", "find_me", "find_me_idx",
    # scoring / capacity
    "score_status", "terminal_capacity",
    # coins
    "compute_treasure_coins", "compute_total_coins",
    # hand helpers
    "hand_counts", "worst_in_hand",
]
