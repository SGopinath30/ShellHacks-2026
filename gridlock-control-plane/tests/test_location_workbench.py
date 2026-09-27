import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.main import app
from app.challenge import routes
from app.challenge.config import get_config
from app.challenge.contracts import ProjectVersion
from app.challenge.engine import haversine
from app.challenge.location_workbench import (LocationVerificationRequest, assess_pair,
                                             qualified_pairs, review_queue)


RECORDS = Path(__file__).resolve().parents[2] / "Badri/output/asus_project_versions/source_backed_needs_review"


def sourced(name,version):
    payload = json.loads((RECORDS/name).read_text())
    return ProjectVersion.model_validate({**payload,"version_id":version,"version_number":1})


def test_reference_points_are_review_tasks_not_qualified_pair():
    desc = sourced("DESC-WINNSBORO-WEST-2025-208-E.json","PV-desc")
    gpc = sourced("GPC-BIG-OGEECHEE-500-230-2026.json","PV-gpc")
    queue = review_queue([desc,gpc])
    assert queue["total"] == 2
    assert "UNRESOLVED_GEOMETRY" in queue["projects"][0]["blockers"]
    assert "STATUS_NOT_ELIGIBLE" in queue["projects"][1]["blockers"]
    config = get_config()
    meters = haversine(desc.geometry.coordinates,gpc.geometry.coordinates,config)
    assessment = assess_pair(desc,gpc,meters,config)
    assert round(assessment["distance"]["meters"]/1000) == 264
    assert assessment["distance"]["kind"] == "REFERENCE_POINT_SEPARATION"
    assert assessment["distance"]["within_configured_maximum"] is False
    assert assessment["qualifies"] is False
    assert qualified_pairs([{"projects":[desc.model_dump(mode="json"),gpc.model_dump(mode="json")]}]) == []


def test_only_verified_close_cross_utility_pair_qualifies():
    desc = sourced("DESC-WINNSBORO-WEST-2025-208-E.json","PV-desc")
    gpc = sourced("GPC-BIG-OGEECHEE-500-230-2026.json","PV-gpc")
    desc = ProjectVersion.model_validate({**desc.model_dump(mode="json"),
                                          "geometry_origin":"UTILITY_GIS","geometry_quality":"HIGH",
                                          "validation_state":"ACCEPTED"})
    gpc = ProjectVersion.model_validate({**gpc.model_dump(mode="json"),
                                         "geometry_origin":"UTILITY_GIS","geometry_quality":"HIGH",
                                         "validation_state":"ACCEPTED","status":"planned"})
    # The geometry is illustrative for this rule test, not a claim about either real project.
    assert assess_pair(desc,gpc,39999)["qualifies"] is True
    assert assess_pair(desc,gpc,40000)["blockers"] == ["OUT_OF_RANGE"]
    pair = {"projects":[desc.model_dump(mode="json"),gpc.model_dump(mode="json")]}
    assert qualified_pairs([pair]) == [pair]


def test_verification_requires_specific_source_and_status_evidence(monkeypatch):
    base = {"base_version_id":"PV-1","actor_id":"asus","actor_role":"Location Reviewer",
            "reason":"Confirmed site in GIS feature","location_text":"Verified project parcel",
            "geometry":{"type":"Point","coordinates":[-81.2,32.0]},
            "geometry_origin":"PUBLIC_GIS","geometry_quality":"HIGH",
            "geometry_evidence":{"source_id":"GIS-42","source_name":"Utility GIS",
                                 "source_url":"https://example.com/gis","page_or_row":"feature 42"}}
    assert LocationVerificationRequest.model_validate(base).geometry_quality.value == "HIGH"
    with pytest.raises(ValidationError):
        LocationVerificationRequest.model_validate({**base,"geometry_evidence":{
            "source_id":"x","source_name":"No URL","page_or_row":"feature 1"}})

    project = sourced("GPC-BIG-OGEECHEE-500-230-2026.json","PV-1")
    class DummyConnection:
        def __enter__(self): return self
        def __exit__(self,*args): return False
    monkeypatch.setattr(routes.repository,"connect",lambda:DummyConnection())
    monkeypatch.setattr(routes.repository,"current_project",lambda *args,**kwargs:project)
    from app.challenge.location_workbench import verify_location
    with pytest.raises(ValueError,match="status change needs separate source evidence"):
        verify_location(project.project_id,LocationVerificationRequest.model_validate({**base,"status":"in_progress"}))


def test_queue_and_assessment_routes(monkeypatch):
    desc = sourced("DESC-WINNSBORO-WEST-2025-208-E.json","PV-desc")
    gpc = sourced("GPC-BIG-OGEECHEE-500-230-2026.json","PV-gpc")
    monkeypatch.setattr(routes.repository,"projects",lambda:[desc,gpc])
    monkeypatch.setattr(routes.repository,"distance_between_current",lambda *args:264000.0)
    client = TestClient(app)
    queue = client.get("/api/v1/location-review-queue").json()
    assert queue["total"] == 2
    assessment = client.get("/api/v1/pair-assessments",params={
        "project_a":desc.project_id,"project_b":gpc.project_id}).json()
    assert assessment["distance"]["kind"] == "REFERENCE_POINT_SEPARATION"
    assert assessment["qualifies"] is False
    page = client.get("/api/v1/location-workbench")
    assert page.status_code == 200
    assert "Excluded Projects" in page.text
    assert "Qualified DESC" in page.text


def test_verification_creates_source_backed_version_and_audit(monkeypatch):
    from app.challenge.location_workbench import verify_location
    project = sourced("GPC-BIG-OGEECHEE-500-230-2026.json","PV-old")
    captured = {}

    class DummyResult:
        def fetchone(self):
            return {"verification_id":uuid4(),"project_id":project.project_id,
                    "from_version_id":"PV-old","to_version_id":"PV-new",
                    "actor_id":"asus","actor_role":"Location Reviewer","reason":"Confirmed parcel",
                    "evidence":{},"occurred_at":datetime.now(timezone.utc)}

    class DummyConnection:
        def __enter__(self): return self
        def __exit__(self,*args): return False
        def execute(self,sql,params):
            captured["audit_sql"] = sql
            return DummyResult()

    monkeypatch.setattr(routes.repository,"connect",lambda:DummyConnection())
    monkeypatch.setattr(routes.repository,"current_project",lambda *args,**kwargs:project)

    def save(conn,candidate,expected_version_id):
        captured["candidate"] = candidate
        captured["expected"] = expected_version_id
        return ProjectVersion.model_validate({**candidate.model_dump(mode="json"),
                                              "version_id":"PV-new","version_number":2})

    monkeypatch.setattr(routes.repository,"save_in_transaction",save)
    request = LocationVerificationRequest.model_validate({
        "base_version_id":"PV-old","actor_id":"asus","actor_role":"Location Reviewer",
        "reason":"Confirmed parcel","location_text":"Big Ogeechee site, west Chatham County",
        "geometry":{"type":"Point","coordinates":[-81.2,32.0]},
        "geometry_origin":"UTILITY_GIS","geometry_quality":"AUTHORITATIVE",
        "geometry_evidence":{"source_id":"GPC-GIS-42","source_name":"GPC site GIS",
                             "source_url":"https://example.com/gis","page_or_row":"feature 42"},
        "status":"in_progress",
        "status_evidence":{"source_id":"GPC-UPDATE","source_name":"GPC update",
                           "source_url":"https://example.com/update","snippet":"Construction ongoing"}})
    result = verify_location(project.project_id,request)
    assert result["project"]["version_id"] == "PV-new"
    assert captured["expected"] == "PV-old"
    assert captured["candidate"].validation_state.value == "ACCEPTED"
    assert captured["candidate"].center_point is None
    assert len(captured["candidate"].evidence) == len(project.evidence)+2
    assert "INSERT INTO synchro.location_verifications" in captured["audit_sql"]
