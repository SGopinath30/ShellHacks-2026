import hashlib
from pathlib import Path

import pytest
from pydantic import ValidationError

from project_intelligence.contracts import (
    AssociationState,
    CandidateProject,
    EvidenceLocator,
    ExtractionMethod,
    FieldEvidence,
    GeometryAssociationStatus,
    GeometryCandidate,
    GeometryOrigin,
    GeometryQuality,
    SourceAccess,
    SourceArtifact,
    SourceType,
    VerificationState,
    VersionComparison,
)
from project_intelligence.extraction.starter_workbook import parse_starter_rows
from project_intelligence.geometry_validation import validate_geometry_candidate
from project_intelligence.phase_bc import (
    PublicSource,
    canonical_geometry_candidate,
    parse_desc_completed_projects,
    parse_desc_planned_projects,
    parse_gpc_projects,
)
from project_intelligence.reconciliation import compare_versions


def _source(tmp_path: Path, utility: str = "DESC") -> PublicSource:
    path = tmp_path / "source.pdf"
    path.write_bytes(b"public source")
    return PublicSource(
        source_version_id="SV-CURRENT",
        utility_id=utility,
        title="Current public source",
        publisher="Utility",
        path=path,
        source_url="https://example.test/source",
        sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        publication_date="2025-01-01",
        access_basis="official public filing",
    )


def _project(utility: str = "GPC") -> CandidateProject:
    source = SourceArtifact(
        source_version_id="SV-PROJECT",
        source_type=SourceType.STARTER_WORKBOOK,
        utility=utility,
        path="starter.xlsx",
        source_access=SourceAccess.PUBLIC,
    )
    return parse_starter_rows(
        [
            {
                "Utility": utility,
                "Project Name": "Kraft - McIntosh 230 kV Rebuild",
                "Voltage": "230 kV",
                "Endpoint A": "Kraft",
                "Endpoint B": "McIntosh",
                "State": "GA",
            }
        ],
        source=source,
    )[0]


def test_desc_planned_project_parser_preserves_labels(tmp_path) -> None:
    text = """
    Project 18 of 47
    Dominion Energy South Carolina
    Planned Transmission Projects $2M and above Total
    5 Year Budget
    Jasper – Okatie 230 kV #2: Construct
    Project ID
    06367 D - G
    Project Description
    Construct a 230 kV line from Jasper to Okatie.
    Project Need
    Reliability.
    Project Status
    In Progress
    Planned In-Service Date
    5/31/2026
    Estimated Project Cost
    """

    projects = parse_desc_planned_projects(
        [{"page_number": 18, "text": text}], _source(tmp_path)
    )

    assert len(projects) == 1
    assert projects[0].external_project_id == "06367 D - G"
    assert projects[0].status_raw == "In Progress"
    assert projects[0].schedule_raw == "5/31/2026"


def test_gpc_parser_distinguishes_need_date_from_start_date(tmp_path) -> None:
    text = """
    2024 GA ITS Ten-Year Plan (2025-2034) Page 63 of 304
    MITCHELL - NORTH TIFTON 230KV RECONDUCTOR
    Teams # 18492
    Need Date 05/01/2025 Start Date 12/31/2021
    Description
    Estimated Cost – ITS Assigned* REDACTED
    * The ITS Assigned designation is for parity forecast purposes only
    Rebuild 35.21 miles of the Mitchell - North Tifton 230kV line.
    REDACTED
    Project advanced in 2025
    PUBLIC DISCLOSURE
    """

    projects = parse_gpc_projects(
        [{"page_number": 233, "text": text}], _source(tmp_path, "GPC")
    )

    assert len(projects) == 1
    assert projects[0].external_project_id == "18492"
    assert projects[0].schedule_label == "Need Date"
    assert projects[0].schedule_raw == "05/01/2025"
    assert projects[0].description.startswith("Rebuild 35.21 miles")


def test_desc_completed_parser_handles_spacing_before_period(tmp_path) -> None:
    text = (
        "vi. Queensboro – Fort Johnson 115KV Rebuild Transmission Line "
        "(Completed and In Service December 2024) . "
        "DESC rebuilt this line to replace aging infrastructure."
    )

    projects = parse_desc_completed_projects(
        [{"page_number": 49, "text": text}], _source(tmp_path)
    )

    assert len(projects) == 1
    assert projects[0].name.startswith("Queensboro")
    assert projects[0].schedule_raw == "December 2024"


def test_candidate_allows_evidence_from_registered_supporting_source() -> None:
    project = _project()
    supporting = FieldEvidence(
        evidence_id="EV-SUPPORT",
        field_path="description",
        source_version_id="SV-SUPPORT",
        locator=EvidenceLocator(page=2),
        original_text="Supporting public evidence",
        normalized_value="Supporting public evidence",
        extraction_method=ExtractionMethod.TEXT_RULE,
        validation_state=VerificationState.VERIFIED_RULE,
        association_state=AssociationState.ASSOCIATION_VERIFIED,
    )
    project.model_copy(
        update={
            "supporting_source_version_ids": ["SV-SUPPORT"],
            "field_evidence": [*project.field_evidence, supporting],
        }
    ).model_validate(
        {
            **project.model_dump(mode="python"),
            "supporting_source_version_ids": ["SV-SUPPORT"],
            "field_evidence": [
                *project.model_dump(mode="python")["field_evidence"],
                supporting.model_dump(mode="python"),
            ],
        }
    )

    with pytest.raises(ValidationError, match="registered candidate source"):
        CandidateProject.model_validate(
            {
                **project.model_dump(mode="python"),
                "field_evidence": [
                    *project.model_dump(mode="python")["field_evidence"],
                    supporting.model_dump(mode="python"),
                ],
            }
        )


def test_osm_route_matching_only_one_endpoint_is_not_accepted() -> None:
    project = _project()
    geometry = GeometryCandidate(
        candidate_geometry_id="GC-ROUTE",
        project_candidate_id=project.candidate_project_id,
        geojson={"type": "LineString", "coordinates": [[-81, 32], [-80, 33]]},
        candidate_feature_name="West McIntosh - Vogtle 230kV",
        provider=GeometryOrigin.OPENSTREETMAP,
        provider_feature_id="way/1",
        discovery_method="OVERPASS",
        quality=GeometryQuality.MEDIUM,
        operator="Georgia Power",
        voltage_kv=230,
    )

    validation = validate_geometry_candidate(project, geometry)

    assert validation.status is GeometryAssociationStatus.NEEDS_REVIEW
    assert "only one verified project endpoint" in " ".join(validation.reasons)


def test_dell_osm_voltage_is_converted_from_volts() -> None:
    geometry = canonical_geometry_candidate(
        {
            "geometry_candidate_id": "GC-1",
            "geometry": {"type": "Point", "coordinates": [-81, 32]},
            "feature_name": "McIntosh Substation",
            "provider_feature_id": "way/1",
            "operator_raw": "Georgia Power",
            "discovery_method": "LOCAL_NAME_FILTER",
            "source_version_id": "SV-OSM",
            "provider_properties": {"voltage": "230000"},
        },
        "CP-CURRENT",
    )

    assert geometry.voltage_kv == 230
    assert geometry.provider is GeometryOrigin.OPENSTREETMAP


def test_missing_current_field_is_unresolved_not_a_destructive_update() -> None:
    previous = _project()
    current = previous.model_copy(update={"state": None})

    comparison = compare_versions(previous, current)

    assert comparison.result is VersionComparison.UNRESOLVED
    assert "state" in comparison.unresolved_fields
