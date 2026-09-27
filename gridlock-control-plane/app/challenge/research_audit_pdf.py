"""Immutable PDF snapshots for project research and human review."""
from __future__ import annotations

import hashlib
import io
import math
import re
from datetime import datetime, timezone
from uuid import UUID, uuid4

from psycopg.types.json import Jsonb
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.platypus import KeepTogether, PageBreak, SimpleDocTemplate, Spacer, Table, TableStyle

from . import repository, research
from .audit_pdf import (AMBER, GREEN, LINE, PALE_AMBER, UTILITY_NAMES,
                        AuditArtifact, AuditExportRequest, MapEvidence,
                        _canonical_hash, _display_time, _field_table,
                        _footer, _label, _paragraph, _point, _styles)


def _public_review(row):
    payload = row.get("payload") or {}
    if row.get("action") == "AUDIT_EXPORTED":
        payload = {key: payload.get(key) for key in
                   ("audit_id", "filename", "snapshot_sha256", "pdf_sha256") if payload.get(key)}
    return {
        "review_id": str(row["review_id"]),
        "action": row["action"],
        "actor_id": row["actor_id"],
        "reason": row["reason"],
        "proposal_hash": row["proposal_hash"],
        "payload": payload,
        "occurred_at": row["occurred_at"].isoformat(),
    }


def capture(proposal_id: UUID | str, actor_id: str, actor_role: str,
            generated_at: datetime | None = None):
    with repository.connect() as conn:
        row = conn.execute(
            "SELECT * FROM synchro.research_proposals WHERE proposal_id=%s", (proposal_id,)
        ).fetchone()
        if row is None:
            raise LookupError("Research record is unknown")
        base = conn.execute(
            "SELECT payload FROM synchro.project_versions WHERE version_id=%s", (row["base_version_id"],)
        ).fetchone()
        current = conn.execute(
            "SELECT payload FROM synchro.project_versions WHERE project_id=%s AND is_current",
            (row["project_id"],),
        ).fetchone()
        reviews = conn.execute(
            """SELECT review_id,action,actor_id,reason,proposal_hash,payload,occurred_at
               FROM synchro.research_reviews WHERE proposal_id=%s ORDER BY occurred_at,review_id""",
            (proposal_id,),
        ).fetchall()
    if base is None:
        raise ValueError("The base project version is unavailable")
    proposal = research.public(row)
    moment = generated_at or datetime.now(timezone.utc)
    review_events = [_public_review(item) for item in reviews]
    latest_decision = next((item for item in reversed(review_events)
                            if item["action"] in {"APPROVE", "REJECT"}), None)
    payload = {
        "schema": "synchro.research-audit.v1",
        "audit_id": str(uuid4()),
        "generated_at": moment.isoformat(),
        "generated_by": {"actor_id": actor_id, "actor_role": actor_role},
        "project": base["payload"],
        "current_project": current["payload"] if current else None,
        "proposal": proposal,
        "latest_review_decision": latest_decision,
        "review_events": review_events,
    }
    return payload, _canonical_hash(payload)


def _distance_meters(a, b):
    point_a, point_b = _point(a), _point(b)
    if point_a is None or point_b is None:
        return None
    lon1, lat1 = map(math.radians, point_a)
    lon2, lat2 = map(math.radians, point_b)
    dlat, dlon = lat2 - lat1, lon2 - lon1
    value = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 6371008.8 * 2 * math.atan2(math.sqrt(value), math.sqrt(1 - value))


def _slug(value):
    result = re.sub(r"[^A-Za-z0-9]+", "-", str(value or "Project")).strip("-")
    return result[:70] or "Project"


def _research_sources(proposal):
    grounding = (proposal.get("research") or {}).get("grounding") or {}
    return [item.get("web") or {} for item in grounding.get("groundingChunks") or []]


def _final_decision(payload):
    proposal = payload["proposal"]
    decision = payload.get("latest_review_decision")
    if decision:
        return _label(decision["action"]), decision.get("reason") or "No reason supplied"
    if proposal["state"] == "FAILED":
        return "Research Failed", proposal.get("error") or "No provider evidence was saved"
    if proposal["state"] == "REVIEW":
        return "Awaiting Human Review", "No project changes have been approved"
    return _label(proposal["state"]), "No separate human decision was recorded"


def render(payload, snapshot_sha256: str) -> bytes:
    styles = _styles()
    output = io.BytesIO()
    document = SimpleDocTemplate(
        output, pagesize=letter, rightMargin=0.62 * inch, leftMargin=0.62 * inch,
        topMargin=0.62 * inch, bottomMargin=0.68 * inch,
        title="SYNCHRO Project Research Audit", author="SYNCHRO Decision Ledger",
    )
    project = payload["project"]
    proposal = payload["proposal"]
    research_data = proposal.get("research") or {}
    draft = proposal.get("payload") or {}
    verification = draft.get("verification") or {}
    decision, decision_reason = _final_decision(payload)
    owner = UTILITY_NAMES.get(project.get("utility_id"), project.get("utility_id", "Unknown utility"))
    stale = ((payload.get("current_project") or {}).get("version_id") != proposal.get("base_version_id")
             and proposal.get("state") != "APPLIED")
    story = []

    story.append(_paragraph("SYNCHRO - Project Evidence Audit", styles["title"]))
    story.append(_paragraph(
        "Immutable snapshot of the project record, AI research outcome, public evidence, and append-only human review history.",
        styles["subtitle"],
    ))
    story.append(_field_table([
        ("Audit ID", payload["audit_id"]),
        ("Generated", _display_time(payload["generated_at"])),
        ("Generated by", f"{payload['generated_by']['actor_role']} - {payload['generated_by']['actor_id']}"),
        ("Research record", proposal["proposal_id"]),
        ("Snapshot SHA-256", snapshot_sha256),
    ], styles))
    story.append(Spacer(1, 14))
    story.append(_paragraph("Executive Audit Summary", styles["h1"]))
    story.append(_field_table([
        ("Project", f"{project.get('project_name')} ({project.get('project_id')})"),
        ("Owner", owner),
        ("Base project version", proposal.get("base_version_id")),
        ("Project status", project.get("status", "unknown")),
        ("Location", project.get("location_text", "Unknown")),
        ("Geometry confidence", f"{project.get('geometry_quality', 'UNKNOWN')} / {project.get('validation_state', 'UNKNOWN')}"),
        ("Research state", proposal.get("state")),
        ("Research model", research_data.get("model") or "No completed model result"),
        ("Final operational decision", decision),
        ("Decision reason", decision_reason),
    ], styles))
    story.append(Spacer(1, 12))
    story.append(_paragraph("Key findings", styles["h2"]))
    story.append(_paragraph(draft.get("summary") or "No research findings were saved for this run.", styles["body"]))
    story.append(_paragraph("Unresolved issues", styles["h2"]))
    missing = list(draft.get("missing_evidence") or [])
    if proposal.get("state") == "FAILED":
        missing.insert(0, proposal.get("error") or "Research did not complete")
    for item in missing or ["No unresolved item was recorded in the saved proposal."]:
        story.append(_paragraph("- " + str(item), styles["body"]))
    if stale:
        warning = Table([[_paragraph(
            "The current project version differs from the base version reviewed here. This PDF preserves the original research context.",
            styles["callout"],
        )]], colWidths=[6.8 * inch])
        warning.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), PALE_AMBER),
                                     ("BOX", (0, 0), (-1, -1), 0.8, AMBER),
                                     ("LEFTPADDING", (0, 0), (-1, -1), 8),
                                     ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                                     ("TOPPADDING", (0, 0), (-1, -1), 7),
                                     ("BOTTOMPADDING", (0, 0), (-1, -1), 7)]))
        story.append(Spacer(1, 8))
        story.append(warning)

    story.append(PageBreak())
    story.append(_paragraph("Comparison / Map Evidence", styles["h1"]))
    proposed_geometry = verification.get("geometry")
    plotted = [{**project, "project_name": "Stored project location"}]
    displacement = _distance_meters(project.get("geometry"), proposed_geometry)
    if proposed_geometry:
        plotted.append({**project, "project_name": "Proposed research location", "geometry": proposed_geometry})
    distance_text = (f"{displacement / 1609.344:.2f} mi change" if displacement is not None
                     else "No measurable location change")
    story.append(MapEvidence(plotted, distance_text))
    story.append(Spacer(1, 10))
    story.append(_field_table([
        ("Stored geometry", str(project.get("geometry") or "Not supplied")),
        ("Proposed geometry", str(proposed_geometry or "No geometry proposal")),
        ("Measured displacement", f"{displacement / 1609.344:.3f} miles" if displacement is not None else "Not calculable"),
        ("Distance usability", "Project-change comparison only; this is not an inter-project opportunity distance."),
        ("Geometry origin", project.get("geometry_origin", "UNKNOWN")),
        ("Geometry quality", project.get("geometry_quality", "UNKNOWN")),
        ("Validation state", project.get("validation_state", "UNKNOWN")),
    ], styles))
    story.append(_paragraph("Geometry warnings", styles["h2"]))
    warnings = []
    if project.get("geometry") is None:
        warnings.append("The saved project version has no geometry.")
    if project.get("geometry_quality") in {"UNRESOLVED", "APPROXIMATE"}:
        warnings.append(f"The saved geometry quality is {project.get('geometry_quality')}.")
    if project.get("validation_state") != "ACCEPTED":
        warnings.append(f"The saved validation state is {project.get('validation_state')}.")
    if project.get("geometry_origin") == "TWO_ENDPOINT_SEGMENT":
        warnings.append("The line is a two-endpoint segment and does not establish a verified route.")
    if proposed_geometry:
        warnings.append("The proposed geometry remains unverified until a human approval creates a new project version.")
    for item in warnings or ["No geometry warning was recorded in this snapshot."]:
        story.append(_paragraph("- " + item, styles["body"]))

    story.append(PageBreak())
    story.append(_paragraph("Evidence Appendix", styles["h1"]))
    story.append(_paragraph("Project version sources", styles["h2"]))
    for index, source in enumerate(project.get("evidence") or [], 1):
        story.append(KeepTogether([_field_table([
            ("Source", f"{index}. {source.get('source_name', 'Unnamed source')} ({source.get('source_id', 'No source ID')})"),
            ("URL", source.get("source_url") or "Not supplied"),
            ("Page / row", source.get("page_or_row") or "Not supplied"),
            ("Supporting excerpt", source.get("snippet") or "Not supplied"),
        ], styles), Spacer(1, 8)]))
    story.append(_paragraph("AI-retrieved sources", styles["h2"]))
    sources = _research_sources(proposal)
    if not sources:
        story.append(_paragraph("No AI-retrieved source was saved. A failed run does not establish evidence.", styles["body"]))
    for index, source in enumerate(sources, 1):
        story.append(_field_table([
            ("Source", f"{index}. {source.get('title') or 'Untitled source'}"),
            ("URL", source.get("uri") or "Not supplied"),
            ("Retrieved", research_data.get("retrieved_on") or "Not supplied"),
        ], styles))
        story.append(Spacer(1, 7))
    gis = research_data.get("gis") or {}
    story.append(_paragraph("GIS / parcel evidence", styles["h2"]))
    story.append(_field_table([
        ("GIS state", gis.get("state") or "No GIS result saved"),
        ("GIS note", gis.get("note") or "No GIS or parcel finding was saved"),
        ("GIS source", gis.get("source_url") or "Not supplied"),
    ], styles))
    if research_data.get("report"):
        story.append(_paragraph("Saved research report", styles["h2"]))
        story.append(_paragraph(research_data["report"], styles["body"]))

    story.append(PageBreak())
    story.append(_paragraph("Audit Trail", styles["h1"]))
    story.append(_paragraph("Material research and review events captured before this export. This section is append-only.", styles["subtitle"]))
    approved = payload.get("current_project") if proposal.get("state") == "APPLIED" else None
    changes = [
        ("Status", project.get("status"), verification.get("status", project.get("status")),
         approved.get("status") if approved else "Not approved"),
        ("Location", project.get("location_text"), verification.get("location_text", project.get("location_text")),
         approved.get("location_text") if approved else "Not approved"),
        ("Geometry quality", project.get("geometry_quality"),
         verification.get("geometry_quality", project.get("geometry_quality")),
         approved.get("geometry_quality") if approved else "Not approved"),
        ("Geometry", str(project.get("geometry") or "Not supplied"),
         str(verification.get("geometry") or "No proposal"),
         str(approved.get("geometry") or "Not approved") if approved else "Not approved"),
    ]
    change_rows = [[_paragraph("Field", styles["table_head"]),
                    _paragraph("Original value", styles["table_head"]),
                    _paragraph("Proposed value", styles["table_head"]),
                    _paragraph("Approved value", styles["table_head"])]]
    change_rows.extend([[_paragraph(value, styles["small"]) for value in row] for row in changes])
    change_table = Table(change_rows, colWidths=[1.0 * inch, 1.95 * inch, 1.95 * inch, 1.9 * inch], repeatRows=1)
    change_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), GREEN), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("VALIGN", (0, 0), (-1, -1), "TOP"), ("GRID", (0, 0), (-1, -1), 0.4, LINE),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F8FBF9")]),
        ("LEFTPADDING", (0, 0), (-1, -1), 5), ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    story.append(_paragraph("Original -> proposed -> approved", styles["h2"]))
    story.append(change_table)
    story.append(Spacer(1, 12))
    story.append(_paragraph("Material events", styles["h2"]))
    rows = [[_paragraph("When", styles["table_head"]), _paragraph("Event", styles["table_head"]),
             _paragraph("Actor", styles["table_head"]), _paragraph("Reason / outcome", styles["table_head"]),
             _paragraph("Proposal hash", styles["table_head"])]]
    rows.append([
        _paragraph(_display_time(proposal.get("created_at")), styles["small"]),
        _paragraph("Research Started", styles["small"]),
        _paragraph("System / Gemini research worker", styles["small"]),
        _paragraph(f"Base version {proposal.get('base_version_id')}", styles["small"]),
        _paragraph(proposal.get("proposal_hash"), styles["small"]),
    ])
    if proposal.get("state") == "FAILED":
        rows.append([
            _paragraph(_display_time(proposal.get("updated_at")), styles["small"]),
            _paragraph("Research Failed", styles["small"]),
            _paragraph("System / Gemini research worker", styles["small"]),
            _paragraph(proposal.get("error") or "No provider evidence was saved", styles["small"]),
            _paragraph(proposal.get("proposal_hash"), styles["small"]),
        ])
    for event in payload.get("review_events") or []:
        rows.append([
            _paragraph(_display_time(event.get("occurred_at")), styles["small"]),
            _paragraph(_label(event.get("action")), styles["small"]),
            _paragraph(event.get("actor_id"), styles["small"]),
            _paragraph(event.get("reason") or "No reason supplied", styles["small"]),
            _paragraph(event.get("proposal_hash"), styles["small"]),
        ])
    audit_table = Table(rows, colWidths=[1.1 * inch, 1.12 * inch, 1.2 * inch, 2.0 * inch, 1.38 * inch], repeatRows=1)
    audit_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), GREEN), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("VALIGN", (0, 0), (-1, -1), "TOP"), ("GRID", (0, 0), (-1, -1), 0.4, LINE),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F8FBF9")]),
        ("LEFTPADDING", (0, 0), (-1, -1), 5), ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(audit_table)
    story.append(Spacer(1, 14))
    story.append(_field_table([
        ("Snapshot SHA-256", snapshot_sha256),
        ("Integrity note", "The PDF byte hash is stored in the append-only research review log and returned in the response header."),
    ], styles))
    document.build(
        story,
        onFirstPage=lambda canvas, doc: _footer(canvas, doc, payload["audit_id"], payload["generated_at"]),
        onLaterPages=lambda canvas, doc: _footer(canvas, doc, payload["audit_id"], payload["generated_at"]),
    )
    return output.getvalue()


def export(proposal_id: UUID | str, request: AuditExportRequest) -> AuditArtifact:
    payload, snapshot_sha256 = capture(proposal_id, request.actor_id, request.actor_role)
    content = render(payload, snapshot_sha256)
    pdf_sha256 = hashlib.sha256(content).hexdigest()
    filename = f"SYNCHRO_Research_Audit_{_slug(payload['project'].get('project_name'))}_{payload['generated_at'][:10]}.pdf"
    details = {
        "audit_id": payload["audit_id"], "generated_at": payload["generated_at"],
        "filename": filename, "snapshot_sha256": snapshot_sha256,
        "pdf_sha256": pdf_sha256, "audit_snapshot": payload,
    }
    with repository.connect() as conn:
        row = conn.execute(
            "SELECT * FROM synchro.research_proposals WHERE proposal_id=%s FOR UPDATE", (proposal_id,)
        ).fetchone()
        if row is None:
            raise LookupError("Research record is unknown")
        if research.digest(row) != payload["proposal"]["proposal_hash"]:
            raise ValueError("Research record changed during export; reload and try again")
        conn.execute(
            """INSERT INTO synchro.research_reviews
               (review_id,proposal_id,action,actor_id,reason,proposal_hash,payload)
               VALUES (%s,%s,'AUDIT_EXPORTED',%s,%s,%s,%s)""",
            (uuid4(), proposal_id, request.actor_id, "Immutable research audit PDF exported",
             payload["proposal"]["proposal_hash"], Jsonb(details)),
        )
    return AuditArtifact(content, filename, payload["audit_id"], payload["generated_at"],
                         snapshot_sha256, pdf_sha256)
