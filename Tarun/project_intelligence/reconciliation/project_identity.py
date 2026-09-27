"""Conservative project-identity reconciliation proposals."""

from __future__ import annotations

import re

from project_intelligence.contracts import (
    CandidateProject,
    ProjectReconciliationProposal,
    ReconciliationDecision,
)


def reconcile_projects(
    left: CandidateProject,
    right: CandidateProject,
) -> ProjectReconciliationProposal:
    if left.utility_id != right.utility_id:
        return _proposal(
            left,
            right,
            ReconciliationDecision.DIFFERENT_PROJECT,
            "utility identifiers differ",
            review=False,
        )
    if left.external_project_id and right.external_project_id:
        if left.external_project_id == right.external_project_id:
            return _proposal(
                left,
                right,
                ReconciliationDecision.SAME_PROJECT,
                "authoritative external project identifiers match",
                review=False,
            )
        return _proposal(
            left,
            right,
            ReconciliationDecision.DIFFERENT_PROJECT,
            "authoritative external project identifiers conflict",
            review=False,
        )

    left_name = _identity_name(left.name.value)
    right_name = _identity_name(right.name.value)
    if left_name and left_name == right_name:
        return _proposal(
            left,
            right,
            ReconciliationDecision.LIKELY_SAME_PROJECT,
            "normalized names match but no authoritative identifier is available",
            review=True,
        )
    return _proposal(
        left,
        right,
        ReconciliationDecision.NEEDS_REVIEW,
        "no authoritative identifier establishes project identity",
        review=True,
    )


def _identity_name(value: str | None) -> str:
    return re.sub(r"[^a-z0-9]+", "", (value or "").casefold())


def _proposal(
    left: CandidateProject,
    right: CandidateProject,
    decision: ReconciliationDecision,
    reason: str,
    *,
    review: bool,
) -> ProjectReconciliationProposal:
    return ProjectReconciliationProposal(
        left_candidate_id=left.candidate_project_id,
        right_candidate_id=right.candidate_project_id,
        decision=decision,
        reasons=[reason],
        requires_human_review=review,
        approved=decision is ReconciliationDecision.SAME_PROJECT and not review,
    )
