from app.strategy.buys import early_province_ok, engine_ready, six_cost_buy
from app.strategy.constants import RUSH_TURN


class DummyGame:  # only used to satisfy six_cost_buy in_stock checks
    class S:
        def __init__(self, q):
            self.quantities = q

    def __init__(self, q):
        self.stock = DummyGame.S(q)


def test_engine_ready_variants():
    assert engine_ready({"gold": 2}) is True
    assert engine_ready({"laboratory": 2}) is True
    assert engine_ready({"market": 1, "festival": 1}) is True
    assert engine_ready({"village": 1, "smithy": 1}) is True
    assert engine_ready({}) is False


def test_early_province_ok_basic():
    counts = {"gold": 2}
    assert early_province_ok(counts, provinces_left=8, turn=12, score_gap=0)


def test_six_cost_buy_prefers_early_hireling_then_dshore_only_with_engine():
    g = DummyGame({"hireling": 10, "distantshore": 10})
    # Early hireling
    assert six_cost_buy(g, coins=6, counts={"hireling": 0}, turn=5) == "BUY hireling"
    # Later: distantshore only if engine ready and not too late
    assert six_cost_buy(g, 6, {"hireling": 1, "gold": 2}, turn=20) == "BUY distantshore"
    # Too late or engine not ready -> None
    assert six_cost_buy(g, 6, {"hireling": 1}, turn=RUSH_TURN - 1) is None
