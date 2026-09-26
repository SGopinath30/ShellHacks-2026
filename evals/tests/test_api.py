from fastapi.testclient import TestClient

from main import InMemoryProjectStore, app


def _client() -> TestClient:
    app.state.project_store = InMemoryProjectStore()
    if hasattr(app.state, "api_extraction_swarm"):
        del app.state.api_extraction_swarm
    return TestClient(app)


def test_extract_validates_and_returns_candidate() -> None:
    response = _client().post(
        "/extract",
        json={
            "name": "North Ridge",
            "description": "North Ridge is planned.",
            "status": "planned",
            "extraction_confidence": 0.8,
        },
    )

    assert response.status_code == 200
    assert response.json()["name"] == "North Ridge"
    assert response.json()["project_type"] == "unknown"


def test_extract_rejects_invalid_confidence() -> None:
    response = _client().post(
        "/extract",
        json={
            "name": "North Ridge",
            "description": "North Ridge is planned.",
            "status": "planned",
            "extraction_confidence": 2,
        },
    )

    assert response.status_code == 422


def test_cors_allows_frontend_requests() -> None:
    response = _client().options(
        "/api/projects",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "GET",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "*"


def test_api_extract_uses_local_mock_and_persists_validated_record(
    monkeypatch,
) -> None:
    monkeypatch.delenv("USE_MODAL_INFERENCE", raising=False)
    client = _client()
    source_text = (
        "On September 15, 2026, the Utility-A Board approved the North Ridge "
        "Substation Project. Utility-A will construct a new electrical substation "
        "at 500 Grid Way in North Ridge, Florida."
    )

    extraction = client.post("/api/extract", json={"text": source_text})

    assert extraction.status_code == 200
    payload = extraction.json()
    assert payload["project"]["name"] == "North Ridge Substation Project"
    assert payload["project"]["status"] == "approved"
    assert payload["project"]["description"] in source_text
    assert payload["project"]["metadata"]["mock_mode"] is True
    assert payload["validation_status"] == "CORRECTED"
    assert payload["evidence"][0]["element_id"] == "element:1"
    assert payload["mock_mode"] is True

    projects = client.get("/api/projects")
    assert projects.status_code == 200
    assert projects.json() == [payload["project"]]


def test_api_extract_rejects_text_without_canonical_project_status() -> None:
    response = _client().post(
        "/api/extract",
        json={"text": "North Ridge Substation may be considered someday."},
    )

    assert response.status_code == 422
