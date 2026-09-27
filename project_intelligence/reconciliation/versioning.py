"""Non-destructive comparison of source-derived project versions."""

from __future__ import annotations

import hashlib

from project_intelligence.contracts import (
    AcceptedProjectVersion,
    CandidateProject,
    ProjectValidationOutcome,
    ProjectValidationResult,
    VersionComparison,
    VersionComparisonResult,
    VerificationState,
)


COMPARABLE_FIELDS = (
    "name",
    "description",
    "voltage_kv",
    "status",
    "project_type",
    "schedule",
    "endpoints",
    "state",
    "county",
    "geometry_candidate",
    "geometry_validation",
)


def compare_versions(
    previous: CandidateProject,
    current: CandidateProject,
) -> VersionComparisonResult:
    changed = []
    unresolved = []
    for field_name in COMPARABLE_FIELDS:
        previous_value = getattr(previous, field_name)
        current_value = getattr(current, field_name)
        if (current_value is None and previous_value is not None) or _unresolved(
            current_value
        ):
            unresolved.append(field_name)
            continue
        if _normalized(previous_value) != _normalized(current_value):
            changed.append(field_name)
    if unresolved:
        result = VersionComparison.UNRESOLVED
    elif changed:
        result = VersionComparison.UPDATED
    else:
        result = VersionComparison.UNCHANGED
    return VersionComparisonResult(
        result=result,
        changed_fields=changed,
        unresolved_fields=unresolved,
    )


def accept_candidate_version(
    candidate: CandidateProject,
    *,
    project_identity: str,
    accepted_by: str,
    previous_version_id: str | None = None,
    validation: ProjectValidationResult | None = None,
) -> AcceptedProjectVersion:
    if validation is None:
        from project_intelligence.validation import validate_candidate

        validation = validate_candidate(candidate)
    if validation.outcome is not ProjectValidationOutcome.ACCEPTED:
        raise ValueError("candidate must pass deterministic validation before acceptance")
    seed = f"{project_identity}|{candidate.source_version_id}|{candidate.candidate_project_id}"
    version_id = f"PV-{hashlib.sha256(seed.encode()).hexdigest()[:14]}"
    return AcceptedProjectVersion(
        project_version_id=version_id,
        project_identity=project_identity,
        candidate=candidate,
        validation=validation,
        accepted_by=accepted_by,
        previous_version_id=previous_version_id,
    )


def _unresolved(value: object) -> bool:
    state = getattr(value, "state", None)
    validation = getattr(value, "validation", None)
    validation_value = getattr(validation, "value", validation)
    return state in {
        VerificationState.UNRESOLVED,
        VerificationState.REJECTED,
    } or validation_value in {"PARTIALLY_FEASIBLE", "INVALID"}


def _normalized(value: object) -> object:
    if value is None:
        return None
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json", exclude={"evidence_ids", "raw"})
    if isinstance(value, list):
        return [_normalized(item) for item in value]
    return value
