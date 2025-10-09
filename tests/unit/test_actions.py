from app.strategy.actions import choose_action
from tests.conftest import GameStub, HandStub, PlayerStub


def test_choose_action_prefers_trashing_then_nonterminal_order():
    # Hand has Chapel (with junk) and Village; should play Chapel first
    hand = HandStub({"chapel": 1, "estate": 1, "village": 1})
    g = GameStub(stock={}, players=[PlayerStub(hand=hand)])
    state = {"actions_left": 1, "action_coins": 0, "extra_buys": 0}
    d = choose_action(g, me_idx=0, state=state)
    assert d == "ACTION chapel"


def test_choose_action_grants_bonuses_on_nonterminal():
    hand = HandStub({"market": 1})
    g = GameStub(stock={}, players=[PlayerStub(hand=hand)])
    state = {"actions_left": 1, "action_coins": 0, "extra_buys": 0}
    d = choose_action(g, 0, state)
    assert d == "ACTION market"
    assert state["action_coins"] >= 1
    assert state["actions_left"] >= 1  # +1 action from Market
