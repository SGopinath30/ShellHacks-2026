"""Contract checks at the Mac to ASUS boundary."""

import json
from pathlib import Path

from integration.handoff import convert
from app.challenge.location_workbench import readiness
from project_intelligence.contracts import (
    AcceptedProjectVersion, GeometryCandidate, GeometryValidation, VersionState,
)


FIXTURE = Path(__file__).resolve().parents[1] / "Tarun/evals/fixtures/accepted_project_version.json"


def accepted_fixture():
    return AcceptedProjectVersion.model_validate(json.loads(FIXTURE.read_text(encoding="utf-8")))


def test_starter_version_remains_review_only_without_geometry():
    source = accepted_fixture()
    project = convert(source)
    assert project.is_fixture
    assert project.geometry is None
    assert project.geometry_quality.value == "UNRESOLVED"
    assert project.validation_state.value == "NEEDS_REVIEW"
    assert project.upstream_project_version_id == source.project_version_id
    assert project.schedule.type == "IN_SERVICE_GAP"
    assert project.evidence[0].source_id == source.candidate.source_version_id
    assert "FIXTURE" in readiness(project)["blockers"]


def test_current_version_with_accepted_project_geometry_maps_to_asus():
    source = accepted_fixture()
    geometry = GeometryCandidate(
        candidate_geometry_id="GEO-1", project_candidate_id=source.candidate.candidate_project_id,
        geojson={"type": "Point", "coordinates": [-81.2, 32.1]},
        provider="UTILITY_GIS", discovery_method="project-specific GIS feature",
        quality="HIGH",
    )
    validation = GeometryValidation(
        candidate_geometry_id="GEO-1", status="ACCEPTED", origin="UTILITY_GIS",
        quality="HIGH", reasons=["project-specific association verified"],
        validation_state="VERIFIED_HUMAN",
    )
    current = source.candidate.model_copy(update={
        "version_state": VersionState.CURRENT_VERIFIED, "geometry_candidate": geometry,
        "geometry_validation": validation,
    })
    version = source.model_copy(update={"candidate": current})
    project = convert(version)
    assert not project.is_fixture
    assert project.geometry.coordinates == (-81.2, 32.1)
    assert project.geometry_origin == "UTILITY_GIS"
    assert project.geometry_quality.value == "HIGH"
    assert project.validation_state.value == "ACCEPTED"
    assert readiness(project)["qualified_ready"]


def test_unaccepted_geometry_cannot_become_qualified():
    source = accepted_fixture()
    geometry = GeometryCandidate(
        candidate_geometry_id="GEO-2", project_candidate_id=source.candidate.candidate_project_id,
        geojson={"type": "LineString", "coordinates": [[-81.2, 32.1], [-81.1, 32.2]]},
        provider="TWO_ENDPOINT_SEGMENT", discovery_method="starter endpoints",
        quality="APPROXIMATE",
    )
    validation = GeometryValidation(
        candidate_geometry_id="GEO-2", status="NEEDS_REVIEW", origin="TWO_ENDPOINT_SEGMENT",
        quality="APPROXIMATE", reasons=["straight segment is not a verified route"],
        validation_state="UNVERIFIED",
    )
    current = source.candidate.model_copy(update={
        "version_state": VersionState.CURRENT_VERIFIED, "geometry_candidate": geometry,
        "geometry_validation": validation,
    })
    project = convert(source.model_copy(update={"candidate": current}))
    assert project.geometry is None
    assert project.validation_state.value == "NEEDS_REVIEW"
    assert "MISSING_GEOMETRY" in readiness(project)["blockers"]
