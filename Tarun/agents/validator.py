"""Evidence-grounded validator agent and trusted record assembler."""

from __future__ import annotations

import hashlib
import json
import re

from agents.extractor import StructuredClient
from extraction.models import (
    CandidateProject,
    DocumentChunk,
    ExtractionAudit,
    IssueSeverity,
    ProjectRecord,
    SourceEvidence,
    ValidationIssue,
    ValidationOutcome,
    ValidationResult,
    ValidatorDecision,
)
from extraction.prompts import (
    VALIDATOR_SYSTEM_PROMPT,
    build_validation_prompt,
)


def validate_record_deterministically(record: dict, source_text: str) -> bool:
    name = record.get("name")
    description = record.get("description")
    status = record.get("status")
    if not all(isinstance(value, str) for value in (name, description, status)):
        return False

    normalized_name = name.strip()
    normalized_description = description.strip()
    normalized_status = status.strip()
    return (
        bool(normalized_name)
        and normalized_name in source_text
        and bool(normalized_description)
        and normalized_description in source_text
        and normalized_status in {"approved", "planned", "proposed"}
        and normalized_status in source_text
    )


class ValidatorAgent:
    """Checks direct evidence and emits records only when required facts resolve."""

    def __init__(self, client: StructuredClient | None = None) -> None:
        self.client = client

    def validate(
        self,
        chunk: DocumentChunk,
        candidate: CandidateProject,
        audit: ExtractionAudit,
    ) -> ValidationResult:
        issues: list[ValidationIssue] = []
        corrections: dict[str, object] = {}
        reviewed = candidate

        if self.client is not None:
            decision = self.client.generate(
                system_prompt=VALIDATOR_SYSTEM_PROMPT,
                user_prompt=build_validation_prompt(
                    chunk,
                    candidate.model_dump_json(),
                    ValidatorDecision.model_json_schema(),
                ),
                response_model=ValidatorDecision,
            )
            reviewed = decision.candidate
            issues.extend(decision.issues)
            corrections.update(decision.corrections)
            if decision.outcome is ValidationOutcome.UNRESOLVED:
                return ValidationResult(
                    outcome=ValidationOutcome.UNRESOLVED,
                    candidate=reviewed,
                    issues=issues,
                    corrections=corrections,
                )

        reviewed = self._apply_authoritative_metadata(
            chunk, reviewed, issues=issues, corrections=corrections
        )
        if not validate_record_deterministically(
            {
                "name": reviewed.project_name,
                "description": reviewed.source_snippet,
                "status": reviewed.status.value,
            },
            chunk.content,
        ):
            issues.append(
                ValidationIssue(
                    code="deterministic_text_mismatch",
                    message="Project name and description must occur verbatim in the source",
                    severity=IssueSeverity.ERROR,
                    field="description",
                )
            )
        reviewed = self._remove_unsupported_evidence(
            chunk, reviewed, issues=issues, corrections=corrections
        )
        self._validate_field_evidence(reviewed, issues=issues)

        missing = {
            "project_name": reviewed.project_name,
            "utility_id": reviewed.utility_id,
            "source_id": reviewed.source_id,
            "source_page_row": reviewed.source_page_row,
        }
        for field, value in missing.items():
            if not value:
                issues.append(
                    ValidationIssue(
                        code="required_field_missing",
                        message=f"{field} is required for a trusted project record",
                        severity=IssueSeverity.ERROR,
                        field=field,
                    )
                )

        snippet = self._evidence_snippet(reviewed)
        if snippet is None:
            issues.append(
                ValidationIssue(
                    code="evidence_missing",
                    message="No verbatim source evidence supports the candidate",
                    severity=IssueSeverity.ERROR,
                    field="source_snippet",
                )
            )

        if any(issue.severity is IssueSeverity.ERROR for issue in issues):
            return ValidationResult(
                outcome=ValidationOutcome.UNRESOLVED,
                candidate=reviewed,
                issues=issues,
                corrections=corrections,
            )

        assert reviewed.project_name is not None
        assert reviewed.utility_id is not None
        assert reviewed.source_id is not None
        assert reviewed.source_page_row is not None
        assert snippet is not None

        project_id = reviewed.project_id or self._stable_project_id(reviewed)
        if reviewed.project_id is None:
            corrections["project_id"] = project_id

        evidence = SourceEvidence(
            source_id=chunk.source_id,
            source_name=chunk.source_name,
            page_or_row=chunk.page_or_row,
            snippet=snippet,
            source_url=chunk.source_url,
            document_hash=chunk.document_hash,
        )
        record = ProjectRecord(
            project_id=project_id,
            utility_id=reviewed.utility_id,
            project_name=reviewed.project_name,
            project_type=reviewed.project_type,
            voltage_kv=reviewed.voltage_kv,
            start_date=reviewed.start_date,
            end_date=reviewed.end_date,
            start_date_precision=reviewed.start_date_precision,
            end_date_precision=reviewed.end_date_precision,
            start_date_text=reviewed.start_date_text,
            end_date_text=reviewed.end_date_text,
            status=reviewed.status,
            geometry=reviewed.geometry,
            location_text=reviewed.location_text,
            source_id=reviewed.source_id,
            source_page_row=reviewed.source_page_row,
            source_snippet=reviewed.source_snippet,
            evidence=[evidence],
            extraction_confidence=reviewed.extraction_confidence,
            audit=audit,
        )
        outcome = ValidationOutcome.CORRECTED if corrections else ValidationOutcome.PASS
        return ValidationResult(
            outcome=outcome,
            candidate=reviewed,
            record=record,
            issues=issues,
            corrections=corrections,
        )

    @staticmethod
    def _apply_authoritative_metadata(
        chunk: DocumentChunk,
        candidate: CandidateProject,
        *,
        issues: list[ValidationIssue],
        corrections: dict[str, object],
    ) -> CandidateProject:
        expected = {
            "utility_id": chunk.utility_id,
            "source_id": chunk.source_id,
            "source_page_row": chunk.page_or_row,
        }
        updates: dict[str, str] = {}
        for field, value in expected.items():
            if getattr(candidate, field) != value:
                updates[field] = value
                corrections[field] = value
                issues.append(
                    ValidationIssue(
                        code="metadata_corrected",
                        message=f"{field} was reset to authoritative chunk metadata",
                        severity=IssueSeverity.WARNING,
                        field=field,
                    )
                )
        field_evidence = [
            item.model_copy(update={"page_or_row": chunk.page_or_row})
            for item in candidate.field_evidence or []
        ]
        if candidate.field_evidence and field_evidence != candidate.field_evidence:
            updates["field_evidence"] = field_evidence
            corrections["field_evidence_page_or_row"] = chunk.page_or_row
        return candidate.model_copy(update=updates) if updates else candidate

    @staticmethod
    def _remove_unsupported_evidence(
        chunk: DocumentChunk,
        candidate: CandidateProject,
        *,
        issues: list[ValidationIssue],
        corrections: dict[str, object],
    ) -> CandidateProject:
        updates: dict[str, object] = {}
        normalized_content = ValidatorAgent._normalize_text(chunk.content)
        if candidate.source_snippet and ValidatorAgent._normalize_text(
            candidate.source_snippet
        ) not in normalized_content:
            updates["source_snippet"] = None
            corrections["source_snippet"] = None
            issues.append(
                ValidationIssue(
                    code="unsupported_quote",
                    message="source_snippet was not copied verbatim from the source",
                    severity=IssueSeverity.WARNING,
                    field="source_snippet",
                )
            )

        supplied_fields = candidate.field_evidence or []
        supported_fields = [
            item
            for item in supplied_fields
            if item.page_or_row == chunk.page_or_row
            and ValidatorAgent._normalize_text(item.quoted_text) in normalized_content
        ]
        if len(supported_fields) != len(supplied_fields):
            updates["field_evidence"] = supported_fields
            corrections["field_evidence"] = [item.model_dump() for item in supported_fields]
            issues.append(
                ValidationIssue(
                    code="unsupported_field_evidence",
                    message="One or more field quotes were absent from the source",
                    severity=IssueSeverity.WARNING,
                    field="field_evidence",
                )
            )
        return candidate.model_copy(update=updates) if updates else candidate

    @staticmethod
    def _validate_field_evidence(
        candidate: CandidateProject,
        *,
        issues: list[ValidationIssue],
    ) -> None:
        supported_values: dict[str, object] = {
            "source_project_id": candidate.source_project_id,
            "project_name": candidate.project_name,
            "project_type": candidate.project_type,
            "voltage_kv": candidate.voltage_kv,
            "start_date": candidate.start_date_text or candidate.start_date,
            "end_date": candidate.end_date_text or candidate.end_date,
            "status": candidate.status,
            "location_text": candidate.location_text,
        }
        for field_name, value in supported_values.items():
            if ValidatorAgent._is_unknown(value):
                continue
            evidence = [
                item
                for item in candidate.field_evidence or []
                if item.field_name == field_name
            ]
            if not evidence:
                continue
            if not any(
                ValidatorAgent._quote_supports(field_name, value, item.quoted_text)
                for item in evidence
            ):
                issues.append(
                    ValidationIssue(
                        code="field_evidence_mismatch",
                        message=f"quoted evidence does not support {field_name}",
                        severity=IssueSeverity.ERROR,
                        field=field_name,
                    )
                )

    @staticmethod
    def _is_unknown(value: object) -> bool:
        if value is None:
            return True
        enum_value = getattr(value, "value", None)
        return enum_value == "unknown"

    @staticmethod
    def _quote_supports(field_name: str, value: object, quote: str) -> bool:
        normalized_quote = ValidatorAgent._normalize_text(quote)
        if field_name == "voltage_kv":
            voltage = f"{float(value):g}"
            return bool(
                re.search(rf"\b{re.escape(voltage)}(?:\.0+)?\s*(?:kv|kilovolts?)\b", normalized_quote)
            )
        if field_name == "start_date":
            start_cues = {"begin", "start", "commence", "construction date"}
            end_cues = {"finish", "complete", "completion", "in-service", "in service"}
            if any(cue in normalized_quote for cue in end_cues) and not any(
                cue in normalized_quote for cue in start_cues
            ):
                return False
        if field_name == "end_date":
            start_cues = {"begin", "start", "commence"}
            end_cues = {"finish", "complete", "completion", "in-service", "in service"}
            if any(cue in normalized_quote for cue in start_cues) and not any(
                cue in normalized_quote for cue in end_cues
            ):
                return False
        raw_value = getattr(value, "value", value)
        normalized_value = ValidatorAgent._normalize_text(str(raw_value).replace("_", " "))
        return normalized_value in normalized_quote

    @staticmethod
    def _normalize_text(value: str) -> str:
        return " ".join(value.casefold().split())

    @staticmethod
    def _evidence_snippet(candidate: CandidateProject) -> str | None:
        if candidate.source_snippet:
            return candidate.source_snippet
        if candidate.field_evidence:
            return candidate.field_evidence[0].quoted_text
        return None

    @staticmethod
    def _stable_project_id(candidate: CandidateProject) -> str:
        identity = json.dumps(
            [candidate.utility_id, candidate.project_name, candidate.source_id],
            ensure_ascii=True,
            separators=(",", ":"),
        )
        return f"project-{hashlib.sha256(identity.encode()).hexdigest()[:16]}"
