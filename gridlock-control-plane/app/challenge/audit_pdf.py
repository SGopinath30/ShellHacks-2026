"""Immutable, source-backed PDF snapshots for the Decision Ledger."""
from __future__ import annotations

import hashlib
import io
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from html import escape
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator
from psycopg.types.json import Jsonb
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.platypus import (Flowable, KeepTogether, PageBreak, Paragraph,
                                SimpleDocTemplate, Spacer, Table, TableStyle)

from . import repository
from .decision_ledger import Decision, context_hash, ledger


GREEN = colors.HexColor("#176B57")
MINT = colors.HexColor("#EAF5EF")
DARK = colors.HexColor("#18362F")
MUTED = colors.HexColor("#61766F")
LINE = colors.HexColor("#D9E7DF")
AMBER = colors.HexColor("#A56516")
PALE_AMBER = colors.HexColor("#FFF5E5")
UTILITY_NAMES = {
    "DESC": "Dominion Energy South Carolina",
    "GPC": "Georgia Power Company",
}


class AuditExportRequest(BaseModel):
    actor_id: str = Field(min_length=1, max_length=200)
    actor_role: str = Field(default="Regional Transmission Planning Manager", min_length=1, max_length=200)

    @field_validator("actor_id", "actor_role")
    @classmethod
    def nonblank(cls, value):
        if not value.strip():
            raise ValueError("Must contain visible text")
        return value.strip()


@dataclass(frozen=True)
class AuditArtifact:
    content: bytes
    filename: str
    audit_id: str
    generated_at: str
    snapshot_sha256: str
    pdf_sha256: str


def _plain(value) -> str:
    if value is None:
        return "Not available"
    text = str(value)
    replacements = {
        "\u2010": "-", "\u2011": "-", "\u2012": "-", "\u2013": "-", "\u2014": "-",
        "\u2018": "'", "\u2019": "'", "\u201c": '"', "\u201d": '"', "\u2026": "...",
        "\u2192": "->", "\u2194": "<->", "\u00a0": " ",
    }
    for source, target in replacements.items():
        text = text.replace(source, target)
    return text.encode("latin-1", "replace").decode("latin-1")


def _markup(value) -> str:
    return escape(_plain(value)).replace("&lt;br/&gt;", "<br/>").replace("\n", "<br/>")


def _label(value) -> str:
    return _plain(value).replace("_", " ").title()


def _canonical_hash(value) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                     allow_nan=False).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _display_time(value) -> str:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(timezone.utc)
        return parsed.strftime("%B %d, %Y at %H:%M UTC")
    except (TypeError, ValueError):
        return _plain(value)


def _slug(projects) -> str:
    names = []
    for project in projects[:2]:
        value = re.sub(r"[^A-Za-z0-9]+", "-", project.get("project_name", "Project")).strip("-")
        names.append(value[:35] or "Project")
    return "__".join(names)[:72]


def _event_snapshot(event):
    value = event.get("snapshot") or {}
    return value if value.get("projects") else None


def capture(pair_id: str, actor_id: str, actor_role: str, generated_at: datetime | None = None):
    history = ledger(pair_id)
    if history is None:
        raise LookupError("Opportunity pair is unknown")
    events = [event for event in history["events"] if event["event_type"] != "AUDIT_EXPORTED"]
    opportunity = next((_event_snapshot(event) for event in events if _event_snapshot(event)), None)
    if opportunity is None:
        raise ValueError("No opportunity analysis snapshot is available for export")
    latest_decision = next((event for event in events
                            if event["event_type"] in Decision._value2member_map_), None)
    moment = generated_at or datetime.now(timezone.utc)
    audit_id = str(uuid4())
    payload = {
        "schema": "synchro.audit.v1",
        "audit_id": audit_id,
        "generated_at": moment.isoformat(),
        "generated_by": {"actor_id": actor_id, "actor_role": actor_role},
        "pair_id": pair_id,
        "current_status": history["current_status"],
        "requires_re_review": history["requires_re_review"],
        "latest_manager_decision": latest_decision,
        "opportunity": opportunity,
        "events": events,
    }
    return payload, _canonical_hash(payload)


def _point(geometry):
    if not geometry:
        return None
    coordinates = geometry.get("coordinates")
    if geometry.get("type") == "Point" and isinstance(coordinates, list) and len(coordinates) >= 2:
        return float(coordinates[0]), float(coordinates[1])
    if geometry.get("type") == "LineString" and coordinates:
        return (sum(float(item[0]) for item in coordinates) / len(coordinates),
                sum(float(item[1]) for item in coordinates) / len(coordinates))
    return None


class MapEvidence(Flowable):
    def __init__(self, projects, distance_text):
        super().__init__()
        self.projects = projects
        self.distance_text = distance_text
        self.width = 6.9 * inch
        self.height = 3.0 * inch

    def draw(self):
        canvas = self.canv
        canvas.setFillColor(colors.HexColor("#F4F8F5"))
        canvas.roundRect(0, 0, self.width, self.height, 9, fill=1, stroke=0)
        canvas.setStrokeColor(colors.HexColor("#D6E5DC"))
        canvas.setLineWidth(0.5)
        for index in range(1, 6):
            x = self.width * index / 6
            canvas.line(x, 0, x, self.height)
        for index in range(1, 4):
            y = self.height * index / 4
            canvas.line(0, y, self.width, y)
        points = [(_point(project.get("geometry")), project) for project in self.projects]
        valid = [item for item in points if item[0] is not None]
        if not valid:
            canvas.setFillColor(MUTED)
            canvas.setFont("Helvetica", 10)
            canvas.drawCentredString(self.width / 2, self.height / 2, "No usable geometry in the audit snapshot")
            return
        xs = [item[0][0] for item in valid]
        ys = [item[0][1] for item in valid]
        dx = max(max(xs) - min(xs), 0.05)
        dy = max(max(ys) - min(ys), 0.05)

        def project(point):
            return (0.7 * inch + (point[0] - min(xs) + dx * 0.15) / (dx * 1.3) * (self.width - 1.4 * inch),
                    0.65 * inch + (point[1] - min(ys) + dy * 0.15) / (dy * 1.3) * (self.height - 1.3 * inch))

        plotted = [(project(point), data) for point, data in valid]
        if len(plotted) >= 2:
            canvas.setStrokeColor(GREEN)
            canvas.setDash(5, 4)
            canvas.setLineWidth(1.2)
            canvas.line(plotted[0][0][0], plotted[0][0][1], plotted[1][0][0], plotted[1][0][1])
            midpoint = ((plotted[0][0][0] + plotted[1][0][0]) / 2,
                        (plotted[0][0][1] + plotted[1][0][1]) / 2)
            width = stringWidth(self.distance_text, "Helvetica-Bold", 8) + 14
            canvas.setFillColor(colors.white)
            canvas.roundRect(midpoint[0] - width / 2, midpoint[1] - 8, width, 16, 5, fill=1, stroke=0)
            canvas.setFillColor(GREEN)
            canvas.setFont("Helvetica-Bold", 8)
            canvas.drawCentredString(midpoint[0], midpoint[1] - 3, self.distance_text)
        for index, (position, project_data) in enumerate(plotted):
            canvas.setFillColor(GREEN if index == 0 else colors.HexColor("#D08A2E"))
            canvas.circle(position[0], position[1], 6, fill=1, stroke=0)
            canvas.setFillColor(DARK)
            canvas.setFont("Helvetica-Bold", 8)
            label = _plain(project_data.get("project_name", "Project"))[:38]
            canvas.drawString(min(position[0] + 10, self.width - 2.35 * inch), position[1] + 2, label)
            point_value = _point(project_data.get("geometry"))
            canvas.setFillColor(MUTED)
            canvas.setFont("Helvetica", 7)
            canvas.drawString(min(position[0] + 10, self.width - 2.35 * inch), position[1] - 9,
                              f"{point_value[1]:.5f}, {point_value[0]:.5f}")
        canvas.setFillColor(MUTED)
        canvas.setFont("Helvetica-Oblique", 7)
        canvas.drawString(8, 7, "Schematic coordinate plot - no basemap and no verified route is implied.")


def _styles():
    sample = getSampleStyleSheet()
    return {
        "title": ParagraphStyle("AuditTitle", parent=sample["Title"], fontName="Helvetica-Bold",
                                fontSize=25, leading=29, textColor=DARK, alignment=TA_LEFT,
                                spaceAfter=12),
        "subtitle": ParagraphStyle("AuditSubtitle", parent=sample["Normal"], fontName="Helvetica",
                                   fontSize=10, leading=15, textColor=MUTED, spaceAfter=16),
        "h1": ParagraphStyle("AuditH1", parent=sample["Heading1"], fontName="Helvetica-Bold",
                             fontSize=17, leading=21, textColor=DARK, spaceBefore=4, spaceAfter=10),
        "h2": ParagraphStyle("AuditH2", parent=sample["Heading2"], fontName="Helvetica-Bold",
                             fontSize=11, leading=14, textColor=GREEN, spaceBefore=10, spaceAfter=6),
        "body": ParagraphStyle("AuditBody", parent=sample["BodyText"], fontName="Helvetica",
                               fontSize=8.5, leading=12, textColor=DARK, spaceAfter=5),
        "small": ParagraphStyle("AuditSmall", parent=sample["BodyText"], fontName="Helvetica",
                                fontSize=7.2, leading=10, textColor=MUTED),
        "table_head": ParagraphStyle("AuditTableHead", parent=sample["BodyText"], fontName="Helvetica-Bold",
                                     fontSize=7.2, leading=9, textColor=colors.white),
        "callout": ParagraphStyle("AuditCallout", parent=sample["BodyText"], fontName="Helvetica-Bold",
                                  fontSize=10, leading=15, textColor=DARK, leftIndent=10, rightIndent=10,
                                  spaceBefore=4, spaceAfter=4),
        "center": ParagraphStyle("AuditCenter", parent=sample["BodyText"], fontName="Helvetica",
                                 fontSize=7.5, leading=10, alignment=TA_CENTER, textColor=MUTED),
    }


def _paragraph(value, style):
    return Paragraph(_markup(value), style)


def _field_table(rows, styles, widths=(1.65 * inch, 5.15 * inch)):
    table = Table([[_paragraph(label, styles["small"]), _paragraph(value, styles["body"])]
                   for label, value in rows], colWidths=list(widths), hAlign="LEFT")
    table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#F4F8F5")),
        ("TEXTCOLOR", (0, 0), (0, -1), MUTED),
        ("GRID", (0, 0), (-1, -1), 0.45, LINE),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
    ]))
    return table


def _geometry_warnings(projects):
    warnings = []
    for project in projects:
        quality = project.get("geometry_quality", "UNKNOWN")
        validation = project.get("validation_state", "UNKNOWN")
        if project.get("geometry") is None:
            warnings.append(f"{project.get('project_name')}: geometry is missing.")
        if quality not in {"VERIFIED", "SURVEYED"}:
            warnings.append(f"{project.get('project_name')}: geometry quality is {quality}.")
        if validation not in {"VERIFIED", "APPROVED"}:
            warnings.append(f"{project.get('project_name')}: validation state is {validation}.")
        if project.get("geometry_origin") == "TWO_ENDPOINT_SEGMENT":
            warnings.append(f"{project.get('project_name')}: the line is a two-endpoint segment, not a verified route.")
    return warnings


def _latest_reason(payload):
    decision = payload.get("latest_manager_decision") or {}
    return decision.get("reason") or "No manager reason has been recorded."


def _footer(canvas, doc, audit_id, generated_at):
    canvas.saveState()
    width, _ = letter
    canvas.setStrokeColor(LINE)
    canvas.line(0.62 * inch, 0.52 * inch, width - 0.62 * inch, 0.52 * inch)
    canvas.setFont("Helvetica", 7)
    canvas.setFillColor(MUTED)
    canvas.drawString(0.62 * inch, 0.34 * inch, f"Audit {audit_id} | Generated {generated_at}")
    canvas.drawRightString(width - 0.62 * inch, 0.34 * inch, f"Page {doc.page}")
    canvas.restoreState()


def render(payload, snapshot_sha256: str) -> bytes:
    styles = _styles()
    output = io.BytesIO()
    document = SimpleDocTemplate(output, pagesize=letter, rightMargin=0.62 * inch,
                                 leftMargin=0.62 * inch, topMargin=0.62 * inch,
                                 bottomMargin=0.68 * inch, title="SYNCHRO Project Evidence Audit",
                                 author="SYNCHRO Decision Ledger")
    opportunity = payload["opportunity"]
    projects = opportunity.get("projects", [])
    distance = opportunity.get("distance") or {}
    warnings = _geometry_warnings(projects)
    story = []

    story.append(_paragraph("SYNCHRO - Project Evidence Audit", styles["title"]))
    story.append(_paragraph("Immutable manager review snapshot with source evidence, spatial analysis, and Decision Ledger history.", styles["subtitle"]))
    story.append(_field_table([
        ("Audit ID", payload["audit_id"]),
        ("Generated", _display_time(payload["generated_at"])),
        ("Generated by", f"{payload['generated_by']['actor_role']} - {payload['generated_by']['actor_id']}"),
        ("Snapshot SHA-256", snapshot_sha256),
        ("Pair ID", payload["pair_id"]),
    ], styles))
    story.append(Spacer(1, 12))
    story.append(_paragraph("Executive Audit Summary", styles["h1"]))
    project_rows = [[_paragraph("Project", styles["table_head"]), _paragraph("Owner", styles["table_head"]),
                     _paragraph("Status", styles["table_head"]), _paragraph("Location / geometry", styles["table_head"])]]
    for project in projects:
        owner = UTILITY_NAMES.get(project.get("utility_id"), project.get("utility_id", "Unknown utility"))
        project_rows.append([
            _paragraph(project.get("project_name"), styles["body"]),
            _paragraph(owner, styles["body"]),
            _paragraph(_label(project.get("status", "UNKNOWN")), styles["body"]),
            _paragraph(f"{project.get('location_text', 'Unknown')}<br/>{project.get('geometry_quality', 'UNKNOWN')} / {project.get('validation_state', 'UNKNOWN')}", styles["body"]),
        ])
    summary_table = Table(project_rows, colWidths=[1.75 * inch, 1.55 * inch, 1.1 * inch, 2.4 * inch], repeatRows=1)
    summary_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), GREEN), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("VALIGN", (0, 0), (-1, -1), "TOP"), ("GRID", (0, 0), (-1, -1), 0.45, LINE),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F8FBF9")]),
        ("LEFTPADDING", (0, 0), (-1, -1), 7), ("RIGHTPADDING", (0, 0), (-1, -1), 7),
        ("TOPPADDING", (0, 0), (-1, -1), 7), ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
    ]))
    story.append(summary_table)
    story.append(_paragraph("Key findings", styles["h2"]))
    findings = [
        f"Measured separation: {float(distance.get('meters', 0)) / 1000:.2f} km ({float(distance.get('display_miles', 0)):.2f} miles) using {_label(distance.get('method', 'UNKNOWN'))}.",
        f"Spatial tier: {_label(opportunity.get('tier', 'UNKNOWN'))}.",
        f"Timing: {_label((opportunity.get('temporal_relationship') or {}).get('status') or (opportunity.get('temporal_relationship') or {}).get('type') or 'UNKNOWN')}.",
        "Possible coordination areas: " + ", ".join(opportunity.get("possible_coordination_areas") or ["None recorded"]),
    ]
    for finding in findings:
        story.append(_paragraph("- " + finding, styles["body"]))
    story.append(_paragraph("Unresolved issues", styles["h2"]))
    unresolved = list(warnings)
    if payload.get("requires_re_review"):
        unresolved.append("Project or analysis data changed after the latest manager decision; re-review is required.")
    if opportunity.get("impact_estimate") is None:
        unresolved.append("No approved impact estimate is attached to this opportunity.")
    if not unresolved:
        unresolved.append("No unresolved issue was recorded in this snapshot.")
    for issue in unresolved:
        story.append(_paragraph("- " + issue, styles["body"]))
    decision_color = PALE_AMBER if payload["current_status"] in {"UNREVIEWED", "NEEDS_MORE_DATA"} else MINT
    decision_table = Table([[_paragraph("Final operational decision", styles["small"]),
                             _paragraph(_label(payload["current_status"]), styles["callout"])],
                            [_paragraph("Reason", styles["small"]), _paragraph(_latest_reason(payload), styles["body"])]],
                           colWidths=[1.65 * inch, 5.15 * inch])
    decision_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), decision_color), ("BOX", (0, 0), (-1, -1), 0.7, LINE),
        ("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8), ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
    ]))
    story.append(Spacer(1, 8))
    story.append(decision_table)

    story.append(PageBreak())
    story.append(_paragraph("Comparison / Map Evidence", styles["h1"]))
    usable = bool(distance.get("meters") is not None and all(project.get("geometry") for project in projects))
    if payload.get("requires_re_review"):
        usability = "REVIEW REQUIRED - a later project or analysis change makes the saved distance stale."
    elif usable:
        usability = "USABLE FOR THIS SAVED SCREENING SNAPSHOT - subject to the geometry warnings below."
    else:
        usability = "NOT USABLE - required geometry or distance evidence is missing."
    story.append(_field_table([
        ("Measured distance", f"{float(distance.get('meters', 0)) / 1000:.2f} km / {float(distance.get('display_miles', 0)):.2f} miles"),
        ("Measurement method", _label(distance.get("method", "UNKNOWN"))),
        ("Distance usability", usability),
        ("Engine version", distance.get("engine_version", "Not recorded")),
        ("Geometry confidence", distance.get("geometry_quality", "Not recorded")),
    ], styles))
    story.append(Spacer(1, 13))
    story.append(MapEvidence(projects, f"{float(distance.get('meters', 0)) / 1000:.2f} km"))
    story.append(Spacer(1, 10))
    story.append(_paragraph("Geometry warnings", styles["h2"]))
    for warning in warnings or ["No geometry warning was recorded in this opportunity snapshot."]:
        story.append(_paragraph("- " + warning, styles["body"]))
    geometry_rows = [[_paragraph("Project / location", styles["table_head"]),
                      _paragraph("Origin", styles["table_head"]),
                      _paragraph("Quality", styles["table_head"]),
                      _paragraph("Validation", styles["table_head"]),
                      _paragraph("Version", styles["table_head"])]]
    for project in projects:
        geometry_rows.append([
            _paragraph(f"{project.get('project_name')}<br/>{project.get('location_text', 'Unknown')}", styles["small"]),
            _paragraph(project.get("geometry_origin", "UNKNOWN"), styles["small"]),
            _paragraph(project.get("geometry_quality", "UNKNOWN"), styles["small"]),
            _paragraph(project.get("validation_state", "UNKNOWN"), styles["small"]),
            _paragraph(project.get("version_id", "Not recorded"), styles["small"]),
        ])
    geometry_table = Table(geometry_rows, colWidths=[2.5 * inch, 1.3 * inch, 0.9 * inch, 1.0 * inch, 1.1 * inch], repeatRows=1)
    geometry_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), GREEN), ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("GRID", (0, 0), (-1, -1), 0.4, LINE),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F8FBF9")]),
        ("LEFTPADDING", (0, 0), (-1, -1), 5), ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(Spacer(1, 8))
    story.append(geometry_table)

    story.append(PageBreak())
    story.append(_paragraph("Evidence Appendix", styles["h1"]))
    for project in projects:
        owner = UTILITY_NAMES.get(project.get("utility_id"), project.get("utility_id", "Unknown utility"))
        story.append(_paragraph(project.get("project_name"), styles["h2"]))
        story.append(_paragraph(f"{owner} | {project.get('project_id')} | Version {project.get('version_id')}", styles["small"]))
        evidence = project.get("evidence") or []
        if not evidence:
            story.append(_paragraph("No source evidence is attached to this project version.", styles["body"]))
        for index, source in enumerate(evidence, 1):
            source_date = source.get("source_date") or source.get("document_date") or source.get("retrieved_at") or "Not supplied"
            rows = [
                ("Source", f"{index}. {source.get('source_name', 'Unnamed source')} ({source.get('source_id', 'No source ID')})"),
                ("URL", source.get("source_url") or "Not supplied"),
                ("Date", source_date),
                ("Page / row", source.get("page_or_row") or "Not supplied"),
                ("Supporting excerpt", source.get("snippet") or "Not supplied"),
            ]
            story.append(KeepTogether([_field_table(rows, styles), Spacer(1, 8)]))
        gis_sources = [source for source in evidence if any(term in
                       (str(source.get("source_name", "")) + str(source.get("source_id", ""))).lower()
                       for term in ("gis", "parcel", "county"))]
        story.append(_paragraph("GIS / parcel evidence", styles["h2"]))
        story.append(_paragraph(
            ", ".join(source.get("source_name", "GIS source") for source in gis_sources)
            if gis_sources else "No explicit GIS or parcel evidence is attached to this project version.", styles["body"]))
    latest = payload.get("latest_manager_decision") or {}
    story.append(_paragraph("Review record", styles["h2"]))
    story.append(_field_table([
        ("Reviewer", f"{latest.get('actor_role', 'No manager decision')} - {latest.get('actor_id', 'Not recorded')}"),
        ("Review timestamp", _display_time(latest.get("occurred_at", "Not recorded"))),
        ("Decision", _label(latest.get("event_type", "UNREVIEWED"))),
        ("Reason", latest.get("reason") or "Not recorded"),
        ("Changes approved", "Operational disposition only; project source fields were not modified by the Decision Ledger."),
    ], styles))

    story.append(PageBreak())
    story.append(_paragraph("Audit Trail", styles["h1"]))
    story.append(_paragraph("Append-only material events captured before this export. Newer database changes do not alter this PDF snapshot.", styles["subtitle"]))
    rows = [[_paragraph("When", styles["table_head"]), _paragraph("Change", styles["table_head"]),
             _paragraph("Original value", styles["table_head"]), _paragraph("Proposed / approved value", styles["table_head"]),
             _paragraph("Who / why", styles["table_head"])]]
    current_status = "UNREVIEWED"
    for event in reversed(payload.get("events", [])):
        kind = event.get("event_type", "UNKNOWN")
        details = event.get("details") or {}
        original = current_status
        proposed = kind
        change = "Operational decision"
        if kind in Decision._value2member_map_:
            current_status = kind
        elif kind == "REASON_UPDATED":
            change = "Decision reason"
            original = details.get("old_reason", "Not recorded")
            proposed = details.get("new_reason", event.get("reason", "Not recorded"))
        elif kind == "PROJECT_VERSION_CHANGED":
            change = f"Project version - {details.get('project_id', 'project')}"
            original = details.get("old_version_id", "Not recorded")
            proposed = details.get("new_version_id", "Not recorded")
        elif kind in {"OPPORTUNITY_CREATED", "OPPORTUNITY_RECOMPUTED"}:
            change = "Analysis snapshot"
            original = details.get("previous_context_hash") or "None"
            proposed = event.get("context_hash", "Not recorded")
        rows.append([
            _paragraph(_display_time(event.get("occurred_at", "Not recorded")), styles["small"]),
            _paragraph(change, styles["small"]),
            _paragraph(_label(original) if change == "Operational decision" else original, styles["small"]),
            _paragraph(_label(proposed) if change == "Operational decision" else proposed, styles["small"]),
            _paragraph(f"{event.get('actor_role', 'Unknown')} - {event.get('actor_id', 'Unknown')}<br/>{event.get('reason') or 'No reason supplied'}", styles["small"]),
        ])
    audit_table = Table(rows, colWidths=[1.05 * inch, 1.12 * inch, 1.35 * inch, 1.45 * inch, 1.83 * inch], repeatRows=1)
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
        ("Integrity note", "The PDF byte hash is stored in the append-only AUDIT_EXPORTED ledger event and returned in the X-SYNCHRO-PDF-SHA256 response header."),
    ], styles))

    document.build(story, onFirstPage=lambda canvas, doc: _footer(canvas, doc, payload["audit_id"], payload["generated_at"]),
                   onLaterPages=lambda canvas, doc: _footer(canvas, doc, payload["audit_id"], payload["generated_at"]))
    return output.getvalue()


def export(pair_id: str, request: AuditExportRequest) -> AuditArtifact:
    payload, snapshot_sha256 = capture(pair_id, request.actor_id, request.actor_role)
    content = render(payload, snapshot_sha256)
    pdf_sha256 = hashlib.sha256(content).hexdigest()
    projects = payload["opportunity"].get("projects", [])
    date_value = payload["generated_at"][:10]
    filename = f"SYNCHRO_Audit_{_slug(projects)}_{date_value}.pdf"
    opportunity = payload["opportunity"]
    event_id = uuid4()
    details = {
        "audit_id": payload["audit_id"], "generated_at": payload["generated_at"],
        "filename": filename, "snapshot_sha256": snapshot_sha256,
        "pdf_sha256": pdf_sha256, "audit_snapshot": payload,
    }
    with repository.connect() as conn:
        pair = conn.execute("SELECT 1 FROM synchro.project_pairs WHERE pair_id=%s FOR UPDATE", (pair_id,)).fetchone()
        if not pair:
            raise LookupError("Opportunity pair is unknown")
        conn.execute("""INSERT INTO synchro.decision_ledger
            (event_id,pair_id,event_type,actor_id,actor_role,reason,snapshot,context_hash,details)
            VALUES (%s,%s,'AUDIT_EXPORTED',%s,%s,'Immutable audit PDF exported',%s,%s,%s)""",
            (event_id, pair_id, request.actor_id, request.actor_role, Jsonb(opportunity),
             context_hash(opportunity), Jsonb(details)))
    return AuditArtifact(content, filename, payload["audit_id"], payload["generated_at"],
                         snapshot_sha256, pdf_sha256)
