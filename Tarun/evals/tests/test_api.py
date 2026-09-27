import json
from pathlib import Path

from fastapi.testclient import TestClient

from main import InMemoryProjectStore, app


def _client() -> TestClient:
    app.state.project_store = InMemoryProjectStore()
    app.state.phase_b_source_verification_path = Path(
        "data/derived/test-missing-phase-b.json"
    )
    app.state.phase_c_geometry_validation_path = Path(
        "data/derived/test-missing-phase-c.json"
    )
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


def test_api_projects_joins_verified_candidates_and_geometry_statuses(
    tmp_path,
) -> None:
    fixture = json.loads(
        Path("evals/fixtures/accepted_project_version.json").read_text(
            encoding="utf-8"
        )
    )
    candidate = fixture["candidate"]
    candidate_id = candidate["candidate_project_id"]
    source_version_id = candidate["source_version_id"]
    verification = {
        "starter_project_id": "STARTER-1",
        "starter_candidate_id": "CP-STARTER-1",
        "current_candidate_id": candidate_id,
        "source_match_score": 1.0,
        "result": "UNCHANGED",
        "changed_fields": [],
        "unresolved_fields": [],
        "reconciliation": {
            "left_candidate_id": "CP-STARTER-1",
            "right_candidate_id": candidate_id,
            "decision": "SAME_PROJECT",
            "reasons": ["Authoritative project ID matches."],
            "requires_human_review": False,
            "approved": True,
        },
        "validation": fixture["validation"],
        "source_version_ids": [source_version_id],
    }
    phase_b = {
        "phase": "B",
        "current_candidates": [candidate],
        "verifications": [verification],
        "sources": [
            {
                "source_version_id": source_version_id,
                "utility_id": "UTILITY-A",
                "title": "Public planning source",
                "publisher": "Utility A",
                "source_url": "https://example.com/public-plan.pdf",
                "sha256": "a" * 64,
                "publication_date": "2026-09-01",
                "source_access": "PUBLIC",
                "access_basis": "Public utility website",
            }
        ],
    }
    geometry_candidate = {
        "candidate_geometry_id": "GC-OSM-1",
        "project_candidate_id": candidate_id,
        "geojson": {"type": "Point", "coordinates": [-81.1, 32.3]},
        "candidate_feature_name": "North Ridge Substation",
        "provider": "OPENSTREETMAP",
        "provider_feature_id": "node/123",
        "discovery_method": "DELL_OSM_HANDOFF",
        "quality": "HIGH",
        "operator": "Utility A",
        "state": "Florida",
        "county": "North Ridge",
        "voltage_kv": 115,
    }
    phase_c = {
        "phase": "C",
        "geometry_validations": [
            {
                "starter_project_id": "STARTER-1",
                "project_candidate_id": candidate_id,
                "dell_project_candidate_id": "DELL-CP-1",
                "geometry_source_version_id": "SV-OSM-1",
                "geometry_candidate": geometry_candidate,
                "validation": {
                    "candidate_geometry_id": "GC-OSM-1",
                    "status": "ACCEPTED",
                    "origin": "OPENSTREETMAP",
                    "quality": "HIGH",
                    "reasons": ["Endpoint, utility, and voltage agree."],
                    "validation_state": "VERIFIED_RULE",
                },
            }
        ],
    }
    phase_b_path = tmp_path / "phase-b.json"
    phase_c_path = tmp_path / "phase-c.json"
    phase_b_path.write_text(json.dumps(phase_b), encoding="utf-8")
    phase_c_path.write_text(json.dumps(phase_c), encoding="utf-8")

    client = _client()
    app.state.phase_b_source_verification_path = phase_b_path
    app.state.phase_c_geometry_validation_path = phase_c_path
    response = client.get("/api/projects")

    assert response.status_code == 200
    projects = response.json()
    assert len(projects) == 1
    assert projects[0]["record_type"] == "verified_candidate"
    assert projects[0]["candidate"]["candidate_project_id"] == candidate_id
    assert projects[0]["candidate"]["field_evidence"] == candidate["field_evidence"]
    assert projects[0]["verification"]["result"] == "UNCHANGED"
    assert projects[0]["sources"][0]["source_url"].endswith("public-plan.pdf")
    assert projects[0]["geometry_statuses"][0]["validation"]["status"] == "ACCEPTED"
    assert projects[0]["geometry_statuses"][0]["geometry_candidate"]["geojson"] == {
        "type": "Point",
        "coordinates": [-81.1, 32.3],
    }


def test_api_extract_rejects_text_without_canonical_project_status() -> None:
    response = _client().post(
        "/api/extract",
        json={"text": "North Ridge Substation may be considered someday."},
    )

    assert response.status_code == 422
