from fastapi.testclient import TestClient

from main import app


def test_extract_validates_and_returns_candidate() -> None:
    response = TestClient(app).post(
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
    response = TestClient(app).post(
        "/extract",
        json={
            "name": "North Ridge",
            "description": "North Ridge is planned.",
            "status": "planned",
            "extraction_confidence": 2,
        },
    )

    assert response.status_code == 422
