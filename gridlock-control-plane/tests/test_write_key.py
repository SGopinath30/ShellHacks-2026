from fastapi.testclient import TestClient
from app.main import app


def test_configured_write_key_protects_all_mutations(monkeypatch):
    monkeypatch.setenv("WRITE_API_KEY", "local-test-secret")
    client = TestClient(app)
    assert client.post("/api/v1/project-versions", json={}).status_code == 401
    assert client.post("/projects", json={}).status_code == 401
    assert client.post("/api/v1/project-versions", json={}, headers={"X-API-Key": "wrong"}).status_code == 401
    # Authorization succeeds; schema validation now handles the empty request.
    assert client.post("/api/v1/project-versions", json={}, headers={"X-API-Key": "local-test-secret"}).status_code == 422
    assert client.get("/docs").status_code == 200


def test_local_writes_remain_open_without_configured_key(monkeypatch):
    monkeypatch.delenv("WRITE_API_KEY", raising=False)
    client = TestClient(app)
    assert client.post("/api/v1/project-versions", json={}).status_code == 422
