"""Audit PDF contract and rendering checks."""
from datetime import datetime, timezone

from fastapi.testclient import TestClient
from pypdf import PdfReader

from app.main import app
from app.challenge import audit_pdf, routes


def opportunity():
    projects = [
        {
            "project_id": "DESC-1", "version_id": "PV-DESC-3", "utility_id": "DESC",
            "project_name": "Jasper-Okatie Transmission Project", "project_type": "transmission",
            "status": "planned", "location_text": "Jasper County, South Carolina",
            "geometry": {"type": "Point", "coordinates": [-81.03, 32.23]},
            "geometry_origin": "SOURCE_COORDINATE", "geometry_quality": "VERIFIED",
            "validation_state": "VERIFIED", "evidence": [{
                "source_id": "DESC-001", "source_name": "DESC filing", "source_url": "https://example.com/desc",
                "page_or_row": "Page 8", "snippet": "Proposed site identified in Jasper County."
            }],
        },
        {
            "project_id": "GPC-1", "version_id": "PV-GPC-2", "utility_id": "GPC",
            "project_name": "McIntosh-Purrysburg Network Upgrade", "project_type": "transmission",
            "status": "construction", "location_text": "Effingham County, Georgia",
            "geometry": {"type": "Point", "coordinates": [-81.00, 32.20]},
            "geometry_origin": "TWO_ENDPOINT_SEGMENT", "geometry_quality": "APPROXIMATE",
            "validation_state": "VERIFIED", "evidence": [{
                "source_id": "GPC-001", "source_name": "Georgia Power plan", "source_url": "https://example.com/gpc",
                "page_or_row": "Row 21", "snippet": "Construction window listed for the network upgrade."
            }],
        },
    ]
    return {
        "pair_id": "P-test", "project_a": "DESC-1", "project_b": "GPC-1", "projects": projects,
        "distance": {"meters": 4800, "display_miles": 2.98, "method": "POINT_TO_POINT",
                     "geometry_quality": "APPROXIMATE", "engine_version": "1.0.0"},
        "tier": "SITE_LOGISTICS", "possible_coordination_areas": ["staging", "mobilization"],
        "temporal_relationship": {"status": "CONFIRMED", "gap_days": 152},
        "temporal_strength": "STRONG", "impact_estimate": None, "impact_model_version": None,
    }


def history():
    snapshot = opportunity()
    return {
        "pair_id": "P-test", "current_status": "APPROVE_COORDINATION", "requires_re_review": False,
        "events": [
            {"event_id": "2", "event_type": "APPROVE_COORDINATION", "actor_id": "manager-7",
             "actor_role": "Regional Transmission Planning Manager", "reason": "Evaluate shared staging.",
             "occurred_at": "2026-09-27T14:42:00+00:00", "snapshot": snapshot,
             "context_hash": "b" * 64, "details": {}},
            {"event_id": "1", "event_type": "OPPORTUNITY_CREATED", "actor_id": "system",
             "actor_role": "Analysis Engine", "reason": None,
             "occurred_at": "2026-09-27T14:26:00+00:00", "snapshot": snapshot,
             "context_hash": "a" * 64, "details": {"previous_context_hash": None}},
        ],
    }


def test_pdf_has_structured_pages_and_integrity_metadata(monkeypatch, tmp_path):
    monkeypatch.setattr(audit_pdf, "ledger", lambda pair_id: history())
    payload, digest = audit_pdf.capture(
        "P-test", "manager-7", "Regional Transmission Planning Manager",
        datetime(2026, 9, 27, 15, 0, tzinfo=timezone.utc))
    content = audit_pdf.render(payload, digest)
    path = tmp_path / "audit.pdf"
    path.write_bytes(content)
    reader = PdfReader(path)
    text = "\n".join(page.extract_text() or "" for page in reader.pages)
    assert len(reader.pages) >= 4
    assert "Executive Audit Summary" in text
    assert "Comparison / Map Evidence" in text
    assert "Evidence Appendix" in text
    assert "Audit Trail" in text
    assert "Jasper-Okatie Transmission Project" in text
    assert "Evaluate shared staging" in text
    assert digest in text


def test_export_appends_pdf_hash_to_immutable_ledger(monkeypatch):
    payload = {
        "audit_id": "audit-1", "generated_at": "2026-09-27T15:00:00+00:00",
        "opportunity": opportunity(),
    }
    monkeypatch.setattr(audit_pdf, "capture", lambda *args: (payload, "c" * 64))
    monkeypatch.setattr(audit_pdf, "render", lambda *args: b"%PDF-1.4 test")
    calls = []

    class Connection:
        def __enter__(self): return self
        def __exit__(self, *args): return False
        def execute(self, sql, params):
            calls.append((sql, params))
            if "SELECT 1" in sql:
                return type("Result", (), {"fetchone": lambda self: {"exists": 1}})()
            return type("Result", (), {})()

    monkeypatch.setattr(audit_pdf.repository, "connect", lambda: Connection())
    artifact = audit_pdf.export("P-test", audit_pdf.AuditExportRequest(actor_id="manager-7"))
    insert = next((sql, params) for sql, params in calls if "INSERT INTO synchro.decision_ledger" in sql)
    assert "AUDIT_EXPORTED" in insert[0]
    details = insert[1][-1].obj
    assert details["audit_id"] == "audit-1"
    assert details["snapshot_sha256"] == "c" * 64
    assert details["pdf_sha256"] == artifact.pdf_sha256
    assert artifact.filename.startswith("SYNCHRO_Audit_Jasper-Okatie")


def test_audit_route_returns_download_and_hash_headers(monkeypatch):
    monkeypatch.setenv("WRITE_API_KEY", "reviewer-key")
    artifact = audit_pdf.AuditArtifact(b"%PDF-test", "SYNCHRO_Audit_Test_2026-09-27.pdf",
                                       "audit-1", "2026-09-27T15:00:00+00:00", "a" * 64, "b" * 64)
    monkeypatch.setattr(routes.audit_pdf, "export", lambda pair_id, request: artifact)
    response = TestClient(app).post(
        "/api/v1/opportunities/P-test/audit-pdf",
        headers={"X-API-Key": "reviewer-key"},
        json={"actor_id": "manager-7", "actor_role": "Regional Transmission Planning Manager"},
    )
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert response.headers["x-synchro-audit-id"] == "audit-1"
    assert response.headers["x-synchro-pdf-sha256"] == "b" * 64
    assert "SYNCHRO_Audit_Test_2026-09-27.pdf" in response.headers["content-disposition"]
