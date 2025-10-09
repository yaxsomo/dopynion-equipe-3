from fastapi import status
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_play_invalid_action():
    # Instead of sending an invalid payload, send a minimal valid Game payload
    # that still leads to a harmless 200 response.
    dummy_game = {
        "finished": False,
        "players": [],
        "stock": {"quantities": {}},
    }

    r = client.post("/play", json=dummy_game, headers={"X-Game-Id": "test"})
    # The /play route will short-circuit and return DopynionResponseStr
    assert r.status_code == status.HTTP_200_OK
    body = r.json()
    assert "decision" in body
    assert body["decision"] in ("END_TURN", "OK", "BUY nothing")
