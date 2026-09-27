"""
Deterministic coordination-opportunity matching engine.

PRD section 11 (pair eligibility), section 14 (flag logic), section 15 (seams).

    eligible(A, B) = A.utility_id != B.utility_id
                     AND A.status is eligible
                     AND B.status is eligible
                     AND sufficient geometry/date quality exists

    flag = spatial_match OR temporal_match

This module never calls out to an LLM. It is pure, reproducible, and
testable: same ProjectRecords + same thresholds => same MatchResults, always
(PRD section 24, Reproducibility).
"""

from __future__ import annotations

from datetime import datetime
from itertools import combinations
from typing import Iterable

from app.models import MatchResult, ProjectRecord, ProjectStatus, ReasonCode
from app.spatial import distance_miles
from app.temporal import overlap_days

INELIGIBLE_STATUSES = {ProjectStatus.CANCELLED}


def is_eligible(project: ProjectRecord) -> bool:
    """A project must have a real status and not be cancelled to be
    considered for matching. (Geometry/date completeness is handled
    per-pair, since a pair can still be flagged on temporal grounds alone
    with no geometry, or vice versa.)"""
    return project.status not in INELIGIBLE_STATUSES


def eligible_pairs(projects: Iterable[ProjectRecord]) -> list[tuple[ProjectRecord, ProjectRecord]]:
    """Cross-utility pairs only -- same-utility projects are excluded."""
    projects = [p for p in projects if is_eligible(p)]
    pairs = []
    for a, b in combinations(projects, 2):
        if a.utility_id != b.utility_id:
            pairs.append((a, b))
    return pairs


def evaluate_pair(
    a: ProjectRecord,
    b: ProjectRecord,
    spatial_threshold_miles: float,
    temporal_min_overlap_days: int,
    seam_buffer_miles: float | None = None,
    boundary_distance_miles: float | None = None,
) -> MatchResult | None:
    """Returns a MatchResult if the pair should be flagged, else None.

    boundary_distance_miles: precomputed distance of this pair's midpoint (or
    nearer project) to the nearest utility/state/RTO boundary. Left as an
    explicit input rather than computed here, since boundary data comes from
    a separate boundary dataset the ingestion team owns -- this function
    stays pure and doesn't reach into external state.
    """
    dist = distance_miles(a.geometry, b.geometry)
    overlap = overlap_days(a.start_date, a.end_date, b.start_date, b.end_date)

    spatial_match = dist is not None and dist <= spatial_threshold_miles
    temporal_match = overlap is not None and overlap >= temporal_min_overlap_days

    if not (spatial_match or temporal_match):
        return None

    reason_codes: list[ReasonCode] = []
    if spatial_match:
        reason_codes.append(ReasonCode.SPATIAL)
    if temporal_match:
        reason_codes.append(ReasonCode.TEMPORAL)

    near_boundary = False
    if (
        seam_buffer_miles is not None
        and boundary_distance_miles is not None
        and boundary_distance_miles <= seam_buffer_miles
    ):
        near_boundary = True
        reason_codes.append(ReasonCode.SEAM)

    if a.voltage_kv is not None and a.voltage_kv == b.voltage_kv:
        reason_codes.append(ReasonCode.SIMILAR_VOLTAGE)

    source_complete = bool(a.evidence and b.evidence)

    return MatchResult(
        match_id=f"M-{a.project_id}-{b.project_id}",
        project_a=a.project_id,
        project_b=b.project_id,
        distance_miles=dist,
        overlap_days=overlap,
        near_boundary=near_boundary,
        boundary_distance_miles=boundary_distance_miles,
        reason_codes=reason_codes,
        spatial_threshold_miles=spatial_threshold_miles,
        temporal_threshold_days=temporal_min_overlap_days,
        source_complete=source_complete,
        computed_at=datetime.utcnow(),
    )


def compute_matches(
    projects: Iterable[ProjectRecord],
    spatial_threshold_miles: float = 25.0,
    temporal_min_overlap_days: int = 90,
    seam_buffer_miles: float | None = 20.0,
    boundary_distances: dict[tuple[str, str], float] | None = None,
) -> list[MatchResult]:
    """Top-level entry point: projects in, flagged MatchResults out.

    boundary_distances: optional lookup keyed by (project_id_a, project_id_b)
    -- or either order -- supplied by the boundary dataset. Absent entries
    just mean Seams Mode won't flag that pair; nothing is fabricated.
    """
    boundary_distances = boundary_distances or {}
    results = []
    for a, b in eligible_pairs(projects):
        bd = boundary_distances.get((a.project_id, b.project_id)) or boundary_distances.get(
            (b.project_id, a.project_id)
        )
        match = evaluate_pair(
            a,
            b,
            spatial_threshold_miles=spatial_threshold_miles,
            temporal_min_overlap_days=temporal_min_overlap_days,
            seam_buffer_miles=seam_buffer_miles,
            boundary_distance_miles=bd,
        )
        if match is not None:
            results.append(match)
    return results
