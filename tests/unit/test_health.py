from fastapi import status
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health():
    r = client.get("/health")
    assert r.status_code == status.HTTP_200_OK
    assert r.json()["status"] == "ok"
