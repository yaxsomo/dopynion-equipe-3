from fastapi import status


def test_buy_state_updates(client):
    headers = {"X-Game-Id": "g-buy-1"}

    # start game + turn
    client.get("/game/start_game", headers=headers)
    client.get("/game/start_turn", headers=headers)

    r = client.get("/game/name")
    assert r.status_code == status.HTTP_200_OK
