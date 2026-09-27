"""Bridge model-facing Nemotron candidates into canonical trust contracts."""

from __future__ import annotations

import hashlib
import re
from typing import Any

from extraction.models import CandidateProject as ModelCandidate
from extraction.models import DocumentChunk
from project_intelligence.contracts import (
    AssociationState,
    CandidateProject,
    CanonicalProjectStatus,
    DateRange,
    EvidenceLocator,
    EvidenceValue,
    ExtractionMethod,
    FieldEvidence,
    ProjectType,
    Schedule,
    ScheduleType,
    VerificationState,
    VersionState,
)
from project_intelligence.evidence.binding import assess_text_association
from project_intelligence.normalization.schedules import (
    construction_window,
    normalize_schedule,
)
from project_intelligence.normalization.status import normalize_status


def to_canonical_candidate(
    candidate: ModelCandidate,
    chunk: DocumentChunk,
) -> CandidateProject:
    source_version_id = str(
        chunk.metadata.get("source_version_id", chunk.source_id)
    )
    evidence: list[FieldEvidence] = []

    def add_evidence(
        *,
        field_path: str,
        original_text: str,
        normalized_value: Any,
        association: AssociationState,
    ) -> str:
        seed = f"{source_version_id}|{chunk.page_or_row}|{field_path}|{original_text}"
        evidence_id = f"EV-{hashlib.sha256(seed.encode()).hexdigest()[:14]}"
        evidence.append(
            FieldEvidence(
                evidence_id=evidence_id,
                field_path=field_path,
                source_version_id=source_version_id,
                locator=_locator(chunk.page_or_row),
                original_text=original_text,
                normalized_value=normalized_value,
                extraction_method=ExtractionMethod.MODEL_EXTRACTION,
                validation_state=_verification_state(association),
                association_state=association,
            )
        )
        return evidence_id

    utility_evidence = add_evidence(
        field_path="utility_id",
        original_text=chunk.utility_id,
        normalized_value=chunk.utility_id,
        association=AssociationState.ASSOCIATION_VERIFIED,
    )

    name_quote = _quote_for(candidate, "project_name") or candidate.source_snippet
    name_association = assess_text_association(
        project_name=candidate.project_name,
        field_value=candidate.project_name,
        quoted_text=name_quote,
        attribute_cues=("project", "substation", "line", candidate.project_name),
    )
    name_evidence = add_evidence(
        field_path="name",
        original_text=name_quote,
        normalized_value=candidate.project_name,
        association=name_association,
    )

    description_association = assess_text_association(
        project_name=candidate.project_name,
        field_value=candidate.source_snippet,
        quoted_text=chunk.content,
        attribute_cues=("construct", "build", "install", "upgrade", "project"),
    )
    description_evidence = add_evidence(
        field_path="description",
        original_text=candidate.source_snippet,
        normalized_value=candidate.source_snippet,
        association=description_association,
    )

    canonical_status = normalize_status(candidate.status.value)
    status_quote = _quote_for(candidate, "status") or candidate.source_snippet
    status_association = assess_text_association(
        project_name=candidate.project_name,
        field_value=candidate.status.value,
        quoted_text=status_quote,
        attribute_cues=(candidate.status.value,),
    )
    status_evidence = add_evidence(
        field_path="status",
        original_text=status_quote,
        normalized_value=canonical_status.value,
        association=status_association,
    )

    voltage_value = None
    if candidate.voltage_kv is not None:
        voltage_quote = _quote_for(candidate, "voltage_kv") or candidate.source_snippet
        voltage_association = assess_text_association(
            project_name=candidate.project_name,
            field_value=f"{candidate.voltage_kv:g}",
            quoted_text=voltage_quote,
            attribute_cues=("kv", "kilovolt", "voltage"),
        )
        voltage_evidence = add_evidence(
            field_path="voltage_kv",
            original_text=voltage_quote,
            normalized_value=candidate.voltage_kv,
            association=voltage_association,
        )
        voltage_value = EvidenceValue[float](
            value=candidate.voltage_kv,
            raw=f"{candidate.voltage_kv:g}",
            state=_verification_state(voltage_association),
            evidence_ids=[voltage_evidence],
        )

    project_type_value = None
    if candidate.project_type.value != "unknown":
        canonical_type = ProjectType(candidate.project_type.value.upper())
        type_quote = _quote_for(candidate, "project_type") or candidate.source_snippet
        type_association = assess_text_association(
            project_name=candidate.project_name,
            field_value=candidate.project_type.value.replace("_", " "),
            quoted_text=type_quote,
            attribute_cues=(candidate.project_type.value.replace("_", " "),),
        )
        type_evidence = add_evidence(
            field_path="project_type",
            original_text=type_quote,
            normalized_value=canonical_type.value,
            association=type_association,
        )
        project_type_value = EvidenceValue[ProjectType](
            value=canonical_type,
            raw=candidate.project_type.value,
            state=_verification_state(type_association),
            evidence_ids=[type_evidence],
        )

    external_project_id_evidence: list[str] = []
    if candidate.source_project_id:
        project_id_quote = (
            _quote_for(candidate, "source_project_id") or candidate.source_snippet
        )
        project_id_association = assess_text_association(
            project_name=candidate.project_name,
            field_value=candidate.source_project_id,
            quoted_text=project_id_quote,
            attribute_cues=("project id", "project number", candidate.source_project_id),
        )
        external_project_id_evidence = [
            add_evidence(
                field_path="external_project_id",
                original_text=project_id_quote,
                normalized_value=candidate.source_project_id,
                association=project_id_association,
            )
        ]

    schedule = _schedule(candidate, chunk, add_evidence)

    candidate_seed = (
        f"{source_version_id}|{chunk.utility_id}|{candidate.project_name}|{chunk.page_or_row}"
    )
    return CandidateProject(
        candidate_project_id=f"CP-{hashlib.sha256(candidate_seed.encode()).hexdigest()[:12]}",
        source_version_id=source_version_id,
        source_access=chunk.source_access,
        utility_id=chunk.utility_id,
        utility_id_evidence_ids=[utility_evidence],
        external_project_id=candidate.source_project_id,
        external_project_id_evidence_ids=external_project_id_evidence,
        name=EvidenceValue[str](
            value=candidate.project_name,
            raw=candidate.project_name,
            state=_verification_state(name_association),
            evidence_ids=[name_evidence],
        ),
        description=EvidenceValue[str](
            value=candidate.source_snippet,
            raw=candidate.source_snippet,
            state=_verification_state(description_association),
            evidence_ids=[description_evidence],
        ),
        voltage_kv=voltage_value,
        status=EvidenceValue[CanonicalProjectStatus](
            value=(
                canonical_status
                if canonical_status is not CanonicalProjectStatus.UNKNOWN
                else None
            ),
            raw=candidate.status.value,
            state=_verification_state(status_association),
            evidence_ids=[status_evidence],
        ),
        project_type=project_type_value,
        schedule=schedule,
        field_evidence=evidence,
        version_state=VersionState.CANDIDATE,
    )


def _quote_for(candidate: ModelCandidate, field_name: str) -> str | None:
    for item in candidate.field_evidence or []:
        if item.field_name == field_name:
            return item.quoted_text
    return None


def _schedule(candidate: ModelCandidate, chunk: DocumentChunk, add_evidence) -> Schedule | None:
    parts: dict[str, Schedule] = {}
    for field_name, label, exact_date in (
        ("start_date", "construction start", candidate.start_date),
        ("end_date", "construction end", candidate.end_date),
    ):
        raw_value = getattr(candidate, f"{field_name}_text") or exact_date
        if raw_value is None:
            continue
        quote = _quote_for(candidate, field_name) or candidate.source_snippet
        association = assess_text_association(
            project_name=candidate.project_name,
            field_value=raw_value,
            quoted_text=chunk.content,
            attribute_cues=(
                "begin" if field_name == "start_date" else "finish",
                "start" if field_name == "start_date" else "complete",
                "construction",
            ),
        )
        evidence_id = add_evidence(
            field_path=f"schedule.{field_name}",
            original_text=quote,
            normalized_value=exact_date or str(raw_value),
            association=association,
        )
        normalized = normalize_schedule(
            raw_value,
            label=label,
            evidence_ids=[evidence_id],
            state=_verification_state(association),
        )
        if normalized:
            parts[field_name] = normalized

    start = parts.get("start_date")
    end = parts.get("end_date")
    if start and end:
        start_range = _schedule_range(start)
        end_range = _schedule_range(end)
        if start_range and end_range:
            states = {start.state, end.state}
            if VerificationState.REJECTED in states:
                state = VerificationState.REJECTED
            elif VerificationState.UNRESOLVED in states:
                state = VerificationState.UNRESOLVED
            else:
                state = VerificationState.VERIFIED_RULE
            return construction_window(
                start=start_range,
                end=end_range,
                raw=f"{start.raw}; {end.raw}",
                evidence_ids=start.evidence_ids + end.evidence_ids,
                state=state,
            )
    return start or end


def _schedule_range(schedule: Schedule) -> DateRange | None:
    if schedule.date:
        return DateRange(earliest=schedule.date, latest=schedule.date)
    return schedule.range


def _verification_state(association: AssociationState) -> VerificationState:
    if association is AssociationState.ASSOCIATION_VERIFIED:
        return VerificationState.VERIFIED_RULE
    if association is AssociationState.ASSOCIATION_FAILED:
        return VerificationState.REJECTED
    return VerificationState.UNRESOLVED


def _locator(page_or_row: str) -> EvidenceLocator:
    page_match = re.fullmatch(r"page:(\d+)", page_or_row)
    row_match = re.fullmatch(r"row:(\d+)", page_or_row)
    return EvidenceLocator(
        page=int(page_match.group(1)) if page_match else None,
        row=int(row_match.group(1)) if row_match else None,
        element_id=page_or_row,
    )
