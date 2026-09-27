"""Project research audit PDF contract and immutable export checks."""
from datetime import datetime, timezone
from uuid import uuid4

import httpx
from fastapi.testclient import TestClient
from pypdf import PdfReader

from app.main import app
from app.challenge import audit_pdf, research, research_audit_pdf, routes


def project():
    return {
        "project_id": "GPC-BIG-OGEECHEE", "version_id": "PV-base-1", "version_number": 1,
        "utility_id": "GPC", "project_name": "Big Ogeechee 500/230 kV Substation",
        "project_type": "substation", "status": "unknown",
        "location_text": "West Chatham County, Georgia",
        "geometry": {"type": "Point", "coordinates": [-81.25, 32.08]},
        "geometry_origin": "SINGLE_LOCATED_POINT", "geometry_quality": "UNRESOLVED",
        "validation_state": "UNRESOLVED", "evidence": [{
            "source_id": "GPC-plan", "source_name": "Georgia Power planning document",
            "source_url": "https://example.com/gpc", "page_or_row": "Page 12",
            "snippet": "Big Ogeechee substation project listed for further confirmation.",
        }],
    }


def failed_payload():
    return {
        "schema": "synchro.research-audit.v1", "audit_id": "audit-research-1",
        "generated_at": "2026-09-27T17:00:00+00:00",
        "generated_by": {"actor_id": "reviewer-4", "actor_role": "Project Evidence Reviewer"},
        "project": project(), "current_project": project(), "latest_review_decision": None,
        "review_events": [],
        "proposal": {
            "proposal_id": str(uuid4()), "project_id": "GPC-BIG-OGEECHEE",
            "base_version_id": "PV-base-1", "proposal_hash": "a" * 64,
            "revision": 1, "state": "FAILED", "payload": {}, "research": {},
            "error": "Gemini quota is temporarily unavailable. Retry after the provider quota resets; no project changes were made.",
            "created_at": "2026-09-27T16:58:00+00:00", "updated_at": "2026-09-27T16:59:00+00:00",
        },
    }


def test_failed_research_pdf_has_all_audit_sections(tmp_path):
    payload = failed_payload()
    content = research_audit_pdf.render(payload, "b" * 64)
    path = tmp_path / "research-audit.pdf"
    path.write_bytes(content)
    reader = PdfReader(path)
    text = "\n".join(page.extract_text() or "" for page in reader.pages)
    assert len(reader.pages) >= 4
    assert "Executive Audit Summary" in text
    assert "Comparison / Map Evidence" in text
    assert "Evidence Appendix" in text
    assert "Audit Trail" in text
    assert "Research Failed" in text
    assert "No AI-retrieved source was saved" in text
    assert "Big Ogeechee" in text
    assert "b" * 64 in text


def test_research_export_appends_hash_to_append_only_review_log(monkeypatch):
    payload = failed_payload()
    monkeypatch.setattr(research_audit_pdf, "capture", lambda *args: (payload, "c" * 64))
    monkeypatch.setattr(research_audit_pdf, "render", lambda *args: b"%PDF-1.4 research")
    monkeypatch.setattr(research, "digest", lambda row: "a" * 64)
    calls = []

    class Connection:
        def __enter__(self): return self
        def __exit__(self, *args): return False
        def execute(self, sql, params=()):
            calls.append((sql, params))
            if "SELECT * FROM synchro.research_proposals" in sql:
                return type("Result", (), {"fetchone": lambda self: {"proposal_id": payload["proposal"]["proposal_id"]}})()
            return type("Result", (), {})()

    monkeypatch.setattr(research_audit_pdf.repository, "connect", lambda: Connection())
    artifact = research_audit_pdf.export(
        payload["proposal"]["proposal_id"], audit_pdf.AuditExportRequest(actor_id="reviewer-4")
    )
    insert = next((sql, params) for sql, params in calls if "INSERT INTO synchro.research_reviews" in sql)
    assert "AUDIT_EXPORTED" in insert[0]
    details = insert[1][-1].obj
    assert details["audit_id"] == "audit-research-1"
    assert details["snapshot_sha256"] == "c" * 64
    assert details["pdf_sha256"] == artifact.pdf_sha256
    assert artifact.filename.startswith("SYNCHRO_Research_Audit_Big-Ogeechee")


def test_research_audit_route_returns_download_headers(monkeypatch):
    monkeypatch.setenv("WRITE_API_KEY", "reviewer-key")
    artifact = audit_pdf.AuditArtifact(
        b"%PDF-test", "SYNCHRO_Research_Audit_Test_2026-09-27.pdf",
        "audit-1", "2026-09-27T17:00:00+00:00", "a" * 64, "b" * 64,
    )
    monkeypatch.setattr(routes.research_audit_pdf, "export", lambda proposal_id, request: artifact)
    response = TestClient(app).post(
        f"/api/v1/research/{uuid4()}/audit-pdf",
        headers={"X-API-Key": "reviewer-key"},
        json={"actor_id": "reviewer-4", "actor_role": "Project Evidence Reviewer"},
    )
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert response.headers["x-synchro-audit-id"] == "audit-1"
    assert response.headers["x-synchro-pdf-sha256"] == "b" * 64


def test_provider_failure_messages_are_actionable_and_safe():
    quota_request = httpx.Request("POST", "https://provider.invalid")
    quota_response = httpx.Response(429, request=quota_request)
    message = research.failure_message(httpx.HTTPStatusError("secret body", request=quota_request,
                                                             response=quota_response))
    assert "quota" in message.lower()
    assert "secret" not in message
    assert "no project changes" in message.lower()
