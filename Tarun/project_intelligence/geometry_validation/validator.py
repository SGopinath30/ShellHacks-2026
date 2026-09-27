"""Conservative utility-project to infrastructure-feature association rules."""

from __future__ import annotations

import re

from project_intelligence.contracts import (
    CandidateProject,
    GeometryAssociationStatus,
    GeometryCandidate,
    GeometryOrigin,
    GeometryQuality,
    GeometryValidation,
    VerificationState,
)
from project_intelligence.normalization.projects import normalize_utility


def attach_validated_geometry(
    project: CandidateProject,
    geometry: GeometryCandidate,
) -> CandidateProject:
    linked_geometry = geometry.model_copy(
        update={"project_candidate_id": project.candidate_project_id}
    )
    validation = validate_geometry_candidate(project, linked_geometry)
    return project.model_copy(
        update={
            "geometry_candidate": linked_geometry,
            "geometry_validation": validation,
        }
    )


def validate_geometry_candidate(
    project: CandidateProject,
    geometry: GeometryCandidate,
) -> GeometryValidation:
    reasons: list[str] = []
    conflicts: list[str] = []
    matches = 0

    if geometry.operator:
        if normalize_utility(geometry.operator) == project.utility_id:
            matches += 1
            reasons.append("geometry operator matches project utility")
        else:
            conflicts.append("geometry operator conflicts with project utility")

    if geometry.voltage_kv is not None and project.voltage_kv and project.voltage_kv.value:
        if geometry.voltage_kv == project.voltage_kv.value:
            matches += 1
            reasons.append("geometry voltage matches project voltage")
        else:
            conflicts.append("geometry voltage conflicts with project voltage")

    for field_name in ("state", "county"):
        project_value = getattr(project, field_name)
        geometry_value = getattr(geometry, field_name)
        if project_value and project_value.value and geometry_value:
            if _normalize(project_value.value) == _normalize(geometry_value):
                matches += 1
                reasons.append(f"geometry {field_name} matches project evidence")
            else:
                conflicts.append(f"geometry {field_name} conflicts with project evidence")

    feature_name = geometry.candidate_feature_name or ""
    project_name_match = bool(
        feature_name
        and project.name.value
        and _name_overlap(feature_name, project.name.value)
    )
    endpoint_matches = [
        endpoint.value
        for endpoint in project.endpoints
        if endpoint.value and _name_overlap(feature_name, endpoint.value)
    ]
    route_geometry = geometry.geojson.get("type") in {
        "LineString",
        "MultiLineString",
    }
    if route_geometry and len(project.endpoints) >= 2:
        if len(endpoint_matches) >= 2:
            matches += 1
            reasons.append("route name matches both verified project endpoints")
        elif endpoint_matches:
            reasons.append(
                "route name matches only one verified project endpoint"
            )
    elif project_name_match or endpoint_matches:
        matches += 1
        reasons.append("feature name matches the project or a verified endpoint")

    if conflicts:
        return GeometryValidation(
            candidate_geometry_id=geometry.candidate_geometry_id,
            status=GeometryAssociationStatus.REJECTED,
            origin=geometry.provider,
            quality=_quality(geometry),
            reasons=conflicts + reasons,
            validation_state=VerificationState.REJECTED,
        )
    if geometry.provider is GeometryOrigin.TWO_ENDPOINT_SEGMENT:
        return GeometryValidation(
            candidate_geometry_id=geometry.candidate_geometry_id,
            status=GeometryAssociationStatus.NEEDS_REVIEW,
            origin=geometry.provider,
            quality=GeometryQuality.APPROXIMATE,
            reasons=reasons
            + ["starter endpoint segments are approximate, not verified routes"],
            validation_state=VerificationState.UNVERIFIED,
        )
    identity_match = (
        len(endpoint_matches) >= 2
        if route_geometry and len(project.endpoints) >= 2
        else project_name_match or bool(endpoint_matches)
    )
    if matches >= 2 and identity_match:
        return GeometryValidation(
            candidate_geometry_id=geometry.candidate_geometry_id,
            status=GeometryAssociationStatus.ACCEPTED,
            origin=geometry.provider,
            quality=_quality(geometry),
            reasons=reasons,
            validation_state=VerificationState.VERIFIED_RULE,
        )
    if matches or endpoint_matches:
        return GeometryValidation(
            candidate_geometry_id=geometry.candidate_geometry_id,
            status=GeometryAssociationStatus.NEEDS_REVIEW,
            origin=geometry.provider,
            quality=_quality(geometry),
            reasons=reasons + ["only one independent association signal matched"],
            validation_state=VerificationState.UNVERIFIED,
        )
    return GeometryValidation(
        candidate_geometry_id=geometry.candidate_geometry_id,
        status=GeometryAssociationStatus.UNRESOLVED,
        origin=geometry.provider,
        quality=_quality(geometry),
        reasons=["no source-backed association signal matched the geometry candidate"],
        validation_state=VerificationState.UNRESOLVED,
    )


def _quality(candidate: GeometryCandidate) -> GeometryQuality:
    if candidate.provider is GeometryOrigin.TWO_ENDPOINT_SEGMENT:
        return GeometryQuality.APPROXIMATE
    return candidate.quality


def _name_overlap(left: str, right: str) -> bool:
    left_tokens = _tokens(left)
    right_tokens = _tokens(right)
    meaningful = {"substation", "project", "line", "transmission", "upgrade"}
    shared = (left_tokens & right_tokens) - meaningful
    return bool(shared)


def _tokens(value: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", value.casefold()))


def _normalize(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.casefold())
