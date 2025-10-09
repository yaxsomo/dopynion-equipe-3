from fastapi import status


def test_health(client):
    r = client.get("/health")
    assert r.status_code == status.HTTP_200_OK
    assert r.json()["status"] == "ok"
