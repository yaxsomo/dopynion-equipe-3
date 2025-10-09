import hypothesis as hp
import hypothesis.strategies as st

from app.strategy.pipeline import choose_buy_action
from tests.conftest import GameStub, PlayerStub


@hp.given(
    coins=st.integers(min_value=0, max_value=12),
    provinces=st.integers(min_value=0, max_value=12),
    golds=st.integers(min_value=0, max_value=12),
)
def test_choose_buy_action_never_crashes_and_returns_string(coins, provinces, golds):
    g = GameStub({"province": provinces, "gold": golds}, [PlayerStub(), PlayerStub()])
    state = {"counts": {}, "turn": 10, "gardens_plan": False}
    out = choose_buy_action(g, coins, 0, state)
    assert isinstance(out, str)
