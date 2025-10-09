from fastapi import status


def test_name(client):
    r = client.get("/game/name")
    assert r.status_code == status.HTTP_200_OK
    assert isinstance(r.json(), str)
    assert "Equipe3" in r.json()


def test_start_game_and_turn(client):
    headers = {"X-Game-Id": "g123"}
    r1 = client.get("/game/start_game", headers=headers)
    assert r1.status_code == status.HTTP_200_OK
    assert r1.json()["decision"] == "OK"

    r2 = client.get("/game/start_turn", headers=headers)
    assert r2.status_code == status.HTTP_200_OK
    assert r2.json()["decision"] == "OK"
