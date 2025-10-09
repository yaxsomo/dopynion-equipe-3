from app.strategy.pipeline import choose_buy_action
from tests.conftest import GameStub, PlayerStub


def test_choose_buy_action_province_when_8_and_ok():
    stock = {"province": 8, "gold": 10}
    players = [PlayerStub(score=0), PlayerStub(score=0)]
    g = GameStub(stock, players)
    state = {"counts": {"gold": 2}, "turn": 12, "gardens_plan": False}
    d = choose_buy_action(g, coins=8, me_idx=0, state=state)
    assert d == "BUY province"


def test_choose_buy_action_gold_when_building():
    stock = {"province": 12, "gold": 10}
    g = GameStub(stock, [PlayerStub(score=0), PlayerStub(score=0)])
    state = {"counts": {"gold": 0}, "turn": 8, "gardens_plan": False}
    d = choose_buy_action(g, coins=8, me_idx=0, state=state)
    assert d == "BUY gold"
