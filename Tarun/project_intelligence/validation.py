"""Deterministic gate between project candidates and ASUS-ready versions."""

from __future__ import annotations

from project_intelligence.contracts import (
    AssociationState,
    CandidateProject,
    GeometryAssociationStatus,
    ProjectValidationIssue,
    ProjectValidationOutcome,
    ProjectValidationResult,
    ScheduleValidationOutcome,
    SourceAccess,
    VerificationState,
)


def validate_candidate(candidate: CandidateProject) -> ProjectValidationResult:
    issues: list[ProjectValidationIssue] = []
    field_states = _field_states(candidate)
    outcome = ProjectValidationOutcome.ACCEPTED

    def add_issue(
        code: str,
        message: str,
        *,
        field_path: str | None,
        state: VerificationState,
        requested_outcome: ProjectValidationOutcome,
    ) -> None:
        nonlocal outcome
        issues.append(
            ProjectValidationIssue(
                code=code,
                message=message,
                field_path=field_path,
                state=state,
            )
        )
        if requested_outcome is ProjectValidationOutcome.REJECTED:
            outcome = ProjectValidationOutcome.REJECTED
        elif outcome is ProjectValidationOutcome.ACCEPTED:
            outcome = ProjectValidationOutcome.NEEDS_REVIEW

    if candidate.source_access is SourceAccess.CEII:
        add_issue(
            "restricted_source",
            "CEII material cannot enter the project-intelligence pipeline",
            field_path=None,
            state=VerificationState.REJECTED,
            requested_outcome=ProjectValidationOutcome.REJECTED,
        )
    elif candidate.source_access is SourceAccess.UNKNOWN:
        add_issue(
            "source_access_unknown",
            "source access must be reviewed before the candidate is ASUS-ready",
            field_path=None,
            state=VerificationState.UNRESOLVED,
            requested_outcome=ProjectValidationOutcome.NEEDS_REVIEW,
        )

    if not candidate.name.value:
        add_issue(
            "project_name_missing",
            "a project name is required",
            field_path="name",
            state=VerificationState.REJECTED,
            requested_outcome=ProjectValidationOutcome.REJECTED,
        )
    elif candidate.name.state not in {
        VerificationState.VERIFIED_RULE,
        VerificationState.VERIFIED_HUMAN,
    }:
        requested = (
            ProjectValidationOutcome.REJECTED
            if candidate.name.state is VerificationState.REJECTED
            else ProjectValidationOutcome.NEEDS_REVIEW
        )
        add_issue(
            "project_name_not_verified",
            "the project name is not bound to verified source evidence",
            field_path="name",
            state=candidate.name.state,
            requested_outcome=requested,
        )

    for field_path, state in field_states.items():
        if field_path == "name":
            continue
        if state is VerificationState.REJECTED:
            add_issue(
                "field_rejected",
                "the populated field conflicts with its source evidence",
                field_path=field_path,
                state=state,
                requested_outcome=ProjectValidationOutcome.REJECTED,
            )

    if candidate.schedule:
        if candidate.schedule.validation is ScheduleValidationOutcome.INVALID:
            add_issue(
                "schedule_invalid",
                "the schedule is impossible or reversed",
                field_path="schedule",
                state=VerificationState.REJECTED,
                requested_outcome=ProjectValidationOutcome.REJECTED,
            )
        elif (
            candidate.schedule.validation
            is ScheduleValidationOutcome.PARTIALLY_FEASIBLE
        ):
            add_issue(
                "schedule_requires_review",
                "the schedule is ambiguous or only partially feasible",
                field_path="schedule",
                state=VerificationState.UNRESOLVED,
                requested_outcome=ProjectValidationOutcome.NEEDS_REVIEW,
            )

    for evidence in candidate.field_evidence:
        if evidence.association_state is AssociationState.ASSOCIATION_FAILED:
            add_issue(
                "evidence_association_failed",
                "the evidence does not bind this value to the project and attribute",
                field_path=evidence.field_path,
                state=VerificationState.REJECTED,
                requested_outcome=ProjectValidationOutcome.REJECTED,
            )
        elif evidence.association_state is AssociationState.ASSOCIATION_AMBIGUOUS:
            add_issue(
                "evidence_association_ambiguous",
                "the evidence does not unambiguously bind this value to the project",
                field_path=evidence.field_path,
                state=VerificationState.UNRESOLVED,
                requested_outcome=ProjectValidationOutcome.NEEDS_REVIEW,
            )

    if candidate.geometry_validation:
        geometry_status = candidate.geometry_validation.status
        if geometry_status is GeometryAssociationStatus.REJECTED:
            add_issue(
                "geometry_rejected",
                "the candidate geometry conflicts with project evidence",
                field_path="geometry_candidate",
                state=VerificationState.REJECTED,
                requested_outcome=ProjectValidationOutcome.REJECTED,
            )
        elif geometry_status is not GeometryAssociationStatus.ACCEPTED:
            add_issue(
                "geometry_requires_review",
                "the candidate geometry association is not verified",
                field_path="geometry_candidate",
                state=candidate.geometry_validation.validation_state,
                requested_outcome=ProjectValidationOutcome.NEEDS_REVIEW,
            )
    elif candidate.geometry_candidate:
        add_issue(
            "geometry_not_validated",
            "candidate geometry must be validated before downstream use",
            field_path="geometry_candidate",
            state=VerificationState.UNVERIFIED,
            requested_outcome=ProjectValidationOutcome.NEEDS_REVIEW,
        )

    return ProjectValidationResult(
        candidate_project_id=candidate.candidate_project_id,
        outcome=outcome,
        field_states=field_states,
        issues=issues,
        ready_for_asus=outcome is ProjectValidationOutcome.ACCEPTED,
    )


def _field_states(candidate: CandidateProject) -> dict[str, VerificationState]:
    fields = {
        "name": candidate.name,
        "description": candidate.description,
        "voltage_kv": candidate.voltage_kv,
        "status": candidate.status,
        "project_type": candidate.project_type,
        "state": candidate.state,
        "county": candidate.county,
    }
    states = {
        field_path: value.state
        for field_path, value in fields.items()
        if value is not None
    }
    for index, endpoint in enumerate(candidate.endpoints):
        states[f"endpoints.{index}"] = endpoint.state
    if candidate.schedule:
        states["schedule"] = candidate.schedule.state
    if candidate.geometry_validation:
        states["geometry_candidate"] = candidate.geometry_validation.validation_state
    return states
