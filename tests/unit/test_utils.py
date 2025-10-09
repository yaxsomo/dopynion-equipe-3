from app.strategy.utils import best_from, terminal_capacity, worst_in_hand


def test_best_from_prefers_priority_then_alpha():
    pick = best_from(["silver", "estate", "gold"])
    assert pick == "gold"


def test_worst_in_hand_prefers_junk_then_copper():
    pick = worst_in_hand(["estate", "copper", "village"])
    assert pick == "estate"


def test_terminal_capacity_simple():
    counts = {
        "village": 1,
        "market": 0,
        "festival": 0,
        "laboratory": 0,
        "smithy": 1,
        "woodcutter": 0,
    }
    # base 1 action +2 from village -1 terminal = 2
    assert terminal_capacity(counts) == 2
