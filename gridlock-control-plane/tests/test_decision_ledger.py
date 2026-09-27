"""Decision contract checks that run without a PostGIS service."""
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.challenge import routes
from app.challenge.decision_ledger import (DecisionRequest, append_decision, context_hash,
                                           snapshot, status_from_events)


def opportunity():
    return {"pair_id": "P-test", "project_a": "DESC-1", "project_b": "GPC-1",
            "projects": [{"project_id": "DESC-1", "version_id": "PV-3"},
                         {"project_id": "GPC-1", "version_id": "PV-2"}],
            "distance": {"meters": 4800, "engine_version": "1.0.0"},
            "tier": "SITE_LOGISTICS",
            "temporal_relationship": {"type": "IN_SERVICE_GAP", "gap_days": 152}}


def test_detail_exposes_immutable_decision_context(monkeypatch):
    monkeypatch.setattr(routes, "selected", lambda *args, **kwargs: [opportunity()])
    detail = TestClient(app).get("/api/v1/opportunities/P-test")
    assert detail.status_code == 200
    body = detail.json()
    assert body["impact_estimate"] is None
    assert body["impact_model_version"] is None
    assert body["decision_context_hash"] == context_hash(snapshot(opportunity()))


def test_stale_context_rejected_before_database_write():
    original = opportunity()
    request = DecisionRequest(action="APPROVE_COORDINATION", actor_id="manager-1",
                              actor_role="Regional Transmission Planning Manager",
                              reason="Evaluate shared staging", decision_context_hash=context_hash(snapshot(original)))
    changed = opportunity()
    changed["projects"][0]["version_id"] = "PV-4"
    with pytest.raises(ValueError, match="refresh"):
        append_decision("P-test", changed, request)


def test_decision_route_passes_current_analysis_to_ledger(monkeypatch):
    monkeypatch.setattr(routes, "selected", lambda *args, **kwargs: [opportunity()])
    captured = {}

    def record(pair_id, current, request):
        captured.update(pair_id=pair_id, current=current, action=request.action.value)
        return {"event_id": "event-1", "event_type": request.action.value}

    monkeypatch.setattr(routes, "append_decision", record)
    body = {"action": "NEEDS_MORE_DATA", "actor_id": "manager-1",
            "actor_role": "Regional Transmission Planning Manager",
            "reason": "Confirm the location", "decision_context_hash": context_hash(snapshot(opportunity()))}
    response = TestClient(app).post("/api/v1/opportunities/P-test/decisions", json=body)
    assert response.status_code == 201
    assert captured == {"pair_id": "P-test", "current": opportunity(), "action": "NEEDS_MORE_DATA"}
    assert response.json()["event_type"] == "NEEDS_MORE_DATA"


def test_decision_requires_reason_and_snapshot_hash():
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        DecisionRequest(action="DISMISS", actor_id="manager-1", actor_role="Manager",
                        reason=" ", decision_context_hash="0" * 64)
    with pytest.raises(ValidationError):
        DecisionRequest(action="DISMISS", actor_id="manager-1", actor_role="Manager",
                        reason="Review complete", decision_context_hash="not-a-hash")


def test_ledger_read_requires_key_when_configured(monkeypatch):
    monkeypatch.setenv("WRITE_API_KEY", "test-private-key")
    monkeypatch.setattr(routes, "ledger", lambda pair_id: {"pair_id": pair_id, "events": []})
    client = TestClient(app)
    assert client.get("/api/v1/opportunities/P-test/decision-ledger").status_code == 401
    response = client.get("/api/v1/opportunities/P-test/decision-ledger",
                          headers={"X-API-Key": "test-private-key"})
    assert response.status_code == 200


def test_source_change_after_approval_requires_new_review():
    events = [{"event_type": "PROJECT_VERSION_CHANGED"},
              {"event_type": "REASON_UPDATED"},
              {"event_type": "APPROVE_COORDINATION"}]
    assert status_from_events(events) == ("APPROVE_COORDINATION", True)
    events.insert(0, {"event_type": "UNDER_REVIEW"})
    assert status_from_events(events) == ("UNDER_REVIEW", False)
