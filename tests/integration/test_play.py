from fastapi import status
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_play_invalid_action():
    r = client.post("/game/play", json={"player_id": "p1", "action": "explode"})
    assert r.status_code == status.HTTP_200_OK
    assert r.json()["valid"] is False
