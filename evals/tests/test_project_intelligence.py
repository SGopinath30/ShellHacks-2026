import json
import sys
from datetime import date
from pathlib import Path

import pytest
from pydantic import ValidationError

from agents.extractor import ExtractorAgent
from evals.project_intelligence import (
    FieldEvaluationCategory,
    categorize_field,
    evaluate_field_categories,
)
from project_intelligence.contracts import (
    AcceptedProjectVersion,
    AssociationState,
    CandidateProject,
    CanonicalProjectStatus,
    DateRange,
    EvidenceValue,
    GeometryAssociationStatus,
    GeometryCandidate,
    GeometryOrigin,
    ProjectType,
    ProjectValidationOutcome,
    ReconciliationDecision,
    ScheduleType,
    SourceAccess,
    SourceArtifact,
    SourceType,
    VerificationState,
    VersionComparison,
)
from project_intelligence.evidence.binding import assess_text_association
from project_intelligence.extraction.starter_workbook import (
    parse_starter_rows,
    parse_starter_workbook,
)
from project_intelligence.extraction.model_adapter import to_canonical_candidate
from project_intelligence.extraction.structured import parse_structured_source
from project_intelligence.geometry_validation import (
    attach_validated_geometry,
    validate_geometry_candidate,
)
from project_intelligence.normalization.schedules import (
    construction_window,
    normalize_schedule,
)
from project_intelligence.reconciliation import (
    accept_candidate_version,
    compare_versions,
    reconcile_projects,
)
from project_intelligence.source_safety import RestrictedSourceError
from project_intelligence.validation import validate_candidate


def _source(access: SourceAccess = SourceAccess.PUBLIC) -> SourceArtifact:
    return SourceArtifact(
        source_version_id="SV-STARTER-1",
        source_type=SourceType.STARTER_WORKBOOK,
        utility="DESC",
        path="starter.xlsx",
        source_access=access,
    )


def _candidate(**updates) -> CandidateProject:
    source_version_id = updates.pop("source_version_id", "SV-STARTER-1")
    source_access = updates.pop("source_access", SourceAccess.PUBLIC)
    source = _source(source_access).model_copy(
        update={"source_version_id": source_version_id}
    )
    candidate = parse_starter_rows(
        [
            {
                "Utility": "DESC",
                "Project Name": "Jasper - Okatie 230 kV #2",
                "Project ID": "DESC-42",
                "Voltage": "230 kV",
                "Status": "In Progress",
                "Project Type": "Transmission Line",
                "In-Service Date": "12/01/2026",
                "Endpoint A": "Jasper",
                "Endpoint B": "Okatie",
                "State": "South Carolina",
            }
        ],
        source=source,
    )[0]
    return candidate.model_copy(update=updates)


def test_starter_rows_parse_without_model_and_bind_field_evidence() -> None:
    candidate = _candidate()

    assert candidate.name.value == "Jasper - Okatie 230 kV #2"
    assert candidate.voltage_kv.value == 230
    assert candidate.status.value is CanonicalProjectStatus.IN_PROGRESS
    assert candidate.project_type.value is ProjectType.TRANSMISSION_LINE
    assert candidate.schedule.type is ScheduleType.IN_SERVICE_MILESTONE
    assert candidate.schedule.date == date(2026, 12, 1)
    assert candidate.version_state.value == "STARTER_DATA"
    assert all(
        item.association_state is AssociationState.ASSOCIATION_VERIFIED
        for item in candidate.field_evidence
    )
    assert validate_candidate(candidate).outcome is ProjectValidationOutcome.ACCEPTED


def test_unknown_structured_values_stay_null_and_retain_evidence() -> None:
    candidate = parse_starter_rows(
        [
            {
                "Utility": "DESC",
                "Project Name": "Jasper - Okatie",
                "Voltage": "not listed",
                "Status": "Awaiting classification",
                "Project Type": "Not specified",
            }
        ],
        source=_source(),
    )[0]

    assert candidate.voltage_kv.value is None
    assert candidate.status.value is None
    assert candidate.project_type.value is None
    assert candidate.voltage_kv.evidence_ids
    assert candidate.status.evidence_ids
    assert candidate.project_type.evidence_ids


def test_real_xlsx_starter_workbook_parses_deterministically(tmp_path) -> None:
    from openpyxl import Workbook

    workbook_path = tmp_path / "starter.xlsx"
    workbook = Workbook()
    worksheet = workbook.active
    worksheet.title = "Projects"
    worksheet.append(
        ["Utility", "Project Name", "Voltage", "Status", "In-Service Date"]
    )
    worksheet.append(
        ["DESC", "Jasper - Okatie 230 kV #2", "230 kV", "In Progress", "Q2 2028"]
    )
    workbook.save(workbook_path)
    source = _source().model_copy(update={"path": str(workbook_path)})

    candidates = parse_starter_workbook(source)

    assert len(candidates) == 1
    assert candidates[0].schedule.type is ScheduleType.IN_SERVICE_MILESTONE
    assert candidates[0].schedule.range.earliest == date(2028, 4, 1)
    assert any(
        evidence.locator.column == "B" and evidence.locator.row == 2
        for evidence in candidates[0].field_evidence
    )


@pytest.mark.parametrize(
    ("source_type", "filename", "content"),
    [
        (
            SourceType.CSV,
            "projects.csv",
            "Utility,Project Name,Voltage,Status,In-Service Date\n"
            "DESC,Jasper - Okatie 230 kV #2,230 kV,In Progress,12/01/2026\n",
        ),
        (
            SourceType.JSON,
            "projects.json",
            json.dumps(
                [
                    {
                        "Utility": "DESC",
                        "Project Name": "Jasper - Okatie 230 kV #2",
                        "Voltage": "230 kV",
                        "Status": "In Progress",
                        "In-Service Date": "12/01/2026",
                    }
                ]
            ),
        ),
    ],
)
def test_csv_and_json_rows_bypass_model_inference(
    tmp_path, source_type, filename, content
) -> None:
    source_path = tmp_path / filename
    source_path.write_text(content)
    source = _source().model_copy(
        update={"source_type": source_type, "path": str(source_path)}
    )

    candidate = parse_structured_source(source)[0]

    assert candidate.voltage_kv.value == 230
    assert candidate.schedule.type is ScheduleType.IN_SERVICE_MILESTONE
    assert all(
        evidence.extraction_method.value == "TABLE_PARSER"
        for evidence in candidate.field_evidence
    )


def test_cli_emits_hashed_candidates_and_validation(tmp_path, monkeypatch) -> None:
    from project_intelligence.cli import main

    source_path = tmp_path / "projects.csv"
    output_path = tmp_path / "candidates.json"
    source_path.write_text(
        "Utility,Project Name,Voltage,Status,In-Service Date\n"
        "DESC,Jasper - Okatie 230 kV #2,230 kV,In Progress,12/01/2026\n"
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "synchro-project-intelligence",
            str(source_path),
            "--source-version-id",
            "SV-CLI-1",
            "--utility",
            "DESC",
            "--source-access",
            "PUBLIC",
            "--output",
            str(output_path),
        ],
    )

    main()

    payload = json.loads(output_path.read_text())
    assert payload["candidate_count"] == 1
    assert len(payload["source"]["downloaded_file_hash"]) == 64
    assert payload["validation"][0]["outcome"] == "ACCEPTED"


def test_quarter_schedule_produces_bounded_milestone_range() -> None:
    schedule = normalize_schedule(
        "Q2 2028",
        label="In-Service Date",
        evidence_ids=["EV-1"],
    )

    assert schedule.type is ScheduleType.IN_SERVICE_MILESTONE
    assert schedule.range.earliest == date(2028, 4, 1)
    assert schedule.range.latest == date(2028, 6, 30)


def test_season_schedule_preserves_coarse_precision() -> None:
    schedule = normalize_schedule(
        "Winter 2028",
        label="Need Date",
        evidence_ids=["EV-1"],
    )

    assert schedule.type is ScheduleType.NEED_DATE_MILESTONE
    assert schedule.precision.value == "SEASON"
    assert schedule.range.earliest == date(2028, 12, 1)
    assert schedule.range.latest == date(2029, 2, 28)


def test_partially_feasible_construction_window_requires_review() -> None:
    schedule = construction_window(
        start=DateRange(earliest=date(2028, 1, 1), latest=date(2028, 6, 30)),
        end=DateRange(earliest=date(2028, 4, 1), latest=date(2028, 12, 31)),
        raw="start H1 2028; end 2028",
        evidence_ids=["EV-1"],
    )

    assert schedule.validation.value == "PARTIALLY_FEASIBLE"


def test_impossible_construction_window_is_invalid() -> None:
    schedule = construction_window(
        start=DateRange(earliest=date(2029, 1, 1), latest=date(2029, 3, 31)),
        end=DateRange(earliest=date(2028, 1, 1), latest=date(2028, 12, 31)),
        raw="start 2029; end 2028",
        evidence_ids=["EV-1"],
    )

    assert schedule.validation.value == "INVALID"


def test_verified_values_require_evidence() -> None:
    with pytest.raises(ValidationError, match="must reference evidence"):
        EvidenceValue[str](value="Jasper", state=VerificationState.VERIFIED_RULE)


def test_nemotron_candidate_is_adapted_with_rule_checked_evidence() -> None:
    from extraction.models import (
        CandidateProject as ModelCandidate,
        DocumentChunk,
        FieldEvidence as ModelFieldEvidence,
        ProjectStatus as ModelStatus,
        ProjectType as ModelProjectType,
    )

    source_text = (
        "The board approved the North Ridge Substation Project. "
        "The North Ridge Substation Project is a new 115 kV substation."
    )
    chunk = DocumentChunk(
        source_id="source-1",
        source_name="plan.pdf",
        utility_id="UTILITY-A",
        page_or_row="page:4",
        content=source_text,
        source_access=SourceAccess.PUBLIC,
        metadata={"source_version_id": "SV-PLAN-1"},
    )
    model_candidate = ModelCandidate(
        name="North Ridge Substation Project",
        description="The board approved the North Ridge Substation Project.",
        status=ModelStatus.APPROVED,
        project_type=ModelProjectType.SUBSTATION,
        voltage_kv=115,
        field_evidence=[
            ModelFieldEvidence(
                field_name="project_name",
                quoted_text="North Ridge Substation Project",
            ),
            ModelFieldEvidence(
                field_name="status",
                quoted_text="approved the North Ridge Substation Project",
            ),
            ModelFieldEvidence(
                field_name="voltage_kv",
                quoted_text="The North Ridge Substation Project is a new 115 kV substation",
            ),
        ],
    )

    canonical = to_canonical_candidate(model_candidate, chunk)

    assert canonical.source_version_id == "SV-PLAN-1"
    assert canonical.name.state is VerificationState.VERIFIED_RULE
    assert canonical.status.state is VerificationState.VERIFIED_RULE
    assert canonical.voltage_kv.state is VerificationState.VERIFIED_RULE
    assert all(
        evidence.extraction_method.value == "MODEL_EXTRACTION"
        for evidence in canonical.field_evidence
    )


def test_nemotron_dates_become_a_construction_window_with_evidence() -> None:
    from extraction.models import (
        CandidateProject as ModelCandidate,
        DocumentChunk,
        FieldEvidence as ModelFieldEvidence,
        ProjectStatus as ModelStatus,
    )

    content = (
        "The approved North Ridge Project will begin construction on April 15, 2028 "
        "and finish construction on December 20, 2029."
    )
    candidate = ModelCandidate(
        name="North Ridge Project",
        description=content,
        status=ModelStatus.APPROVED,
        start_date="2028-04-15",
        end_date="2029-12-20",
        start_date_text="April 15, 2028",
        end_date_text="December 20, 2029",
        field_evidence=[
            ModelFieldEvidence(field_name="start_date", quoted_text="April 15, 2028"),
            ModelFieldEvidence(field_name="end_date", quoted_text="December 20, 2029"),
        ],
    )
    chunk = DocumentChunk(
        source_id="source-1",
        source_name="plan.pdf",
        utility_id="UTILITY-A",
        page_or_row="page:4",
        content=content,
        source_access=SourceAccess.PUBLIC,
    )

    canonical = to_canonical_candidate(candidate, chunk)

    assert canonical.schedule.type is ScheduleType.CONSTRUCTION_WINDOW
    assert canonical.schedule.start.earliest == date(2028, 4, 15)
    assert canonical.schedule.end.latest == date(2029, 12, 20)
    assert len(canonical.schedule.evidence_ids) == 2


def test_text_association_requires_project_value_and_attribute_context() -> None:
    assert assess_text_association(
        project_name="Jasper - Okatie",
        field_value=230,
        quoted_text="The Jasper - Okatie project is a new 230 kV transmission line.",
        attribute_cues=("kV", "voltage"),
    ) is AssociationState.ASSOCIATION_VERIFIED
    assert assess_text_association(
        project_name="Jasper - Okatie",
        field_value=230,
        quoted_text="Nearby facilities include 230 kV equipment.",
        attribute_cues=("kV", "voltage"),
    ) is AssociationState.ASSOCIATION_AMBIGUOUS


def test_name_only_reconciliation_requires_human_review() -> None:
    left = _candidate(external_project_id=None)
    right = left.model_copy(
        update={"candidate_project_id": "CP-OTHER", "source_version_id": "SV-2"}
    )

    proposal = reconcile_projects(left, right)

    assert proposal.decision is ReconciliationDecision.LIKELY_SAME_PROJECT
    assert proposal.requires_human_review is True
    assert proposal.approved is False


def test_authoritative_project_id_can_reconcile_automatically() -> None:
    left = _candidate()
    right = left.model_copy(update={"candidate_project_id": "CP-OTHER"})

    proposal = reconcile_projects(left, right)

    assert proposal.decision is ReconciliationDecision.SAME_PROJECT
    assert proposal.approved is True


def test_new_source_data_is_compared_without_overwriting() -> None:
    previous = _candidate()
    current = previous.model_copy(
        update={
            "candidate_project_id": "CP-NEW",
            "source_version_id": "SV-NEW",
            "status": previous.status.model_copy(
                update={"value": CanonicalProjectStatus.COMPLETED}
            ),
        }
    )

    comparison = compare_versions(previous, current)

    assert comparison.result is VersionComparison.UPDATED
    assert comparison.changed_fields == ["status"]
    assert previous.status.value is CanonicalProjectStatus.IN_PROGRESS


def test_accepting_new_source_creates_linked_immutable_version() -> None:
    first = accept_candidate_version(
        _candidate(),
        project_identity="DESC-42",
        accepted_by="reviewer@example.com",
    )
    updated_candidate = _candidate(
        candidate_project_id="CP-UPDATED",
        source_version_id="SV-UPDATED",
    )
    second = accept_candidate_version(
        updated_candidate,
        project_identity="DESC-42",
        accepted_by="reviewer@example.com",
        previous_version_id=first.project_version_id,
    )

    assert second.project_version_id != first.project_version_id
    assert second.previous_version_id == first.project_version_id
    assert second.validation.ready_for_asus is True


def test_geometry_validation_accepts_multiple_matching_signals() -> None:
    project = _candidate()
    geometry = GeometryCandidate(
        candidate_geometry_id="GC-1",
        geojson={"type": "Point", "coordinates": [-80.9, 32.3]},
        candidate_feature_name="Okatie Substation",
        provider=GeometryOrigin.OPENSTREETMAP,
        provider_feature_id="node/123",
        discovery_method="OVERPASS",
        operator="DESC",
        state="South Carolina",
        voltage_kv=230,
    )

    validation = validate_geometry_candidate(project, geometry)

    assert validation.status is GeometryAssociationStatus.ACCEPTED
    assert validation.validation_state is VerificationState.VERIFIED_RULE

    attached = attach_validated_geometry(project, geometry)
    assert attached.geometry_candidate.project_candidate_id == project.candidate_project_id
    assert validate_candidate(attached).outcome is ProjectValidationOutcome.ACCEPTED


def test_geometry_validation_rejects_conflicting_operator() -> None:
    project = _candidate()
    geometry = GeometryCandidate(
        candidate_geometry_id="GC-2",
        geojson={"type": "Point", "coordinates": [-80.9, 32.3]},
        candidate_feature_name="Okatie Substation",
        provider=GeometryOrigin.OPENSTREETMAP,
        discovery_method="OVERPASS",
        operator="Different Utility",
    )

    assert (
        validate_geometry_candidate(project, geometry).status
        is GeometryAssociationStatus.REJECTED
    )


def test_ceii_starter_source_is_rejected() -> None:
    with pytest.raises(RestrictedSourceError):
        parse_starter_rows(
            [{"Project Name": "Restricted Project"}],
            source=_source(SourceAccess.CEII),
        )


def test_unknown_source_access_requires_review() -> None:
    candidate = _candidate(source_access=SourceAccess.UNKNOWN)

    validation = validate_candidate(candidate)

    assert validation.outcome is ProjectValidationOutcome.NEEDS_REVIEW
    assert validation.ready_for_asus is False


def test_ceii_chunk_never_reaches_remote_client() -> None:
    class FailingClient:
        def generate(self, **kwargs):
            raise AssertionError("client must not be called")

    from extraction.models import DocumentChunk

    chunk = DocumentChunk(
        source_id="restricted",
        source_name="restricted.pdf",
        utility_id="utility-a",
        page_or_row="page:1",
        content="Restricted Project is approved.",
        source_access=SourceAccess.CEII,
    )
    extractor = ExtractorAgent(
        FailingClient(), model="remote-model", provider="remote-provider"
    )

    with pytest.raises(RestrictedSourceError):
        extractor.extract(chunk)


def test_unknown_source_never_reaches_remote_client() -> None:
    class FailingClient:
        def generate(self, **kwargs):
            raise AssertionError("client must not be called")

    from extraction.models import DocumentChunk

    chunk = DocumentChunk(
        source_id="unclassified",
        source_name="unclassified.pdf",
        utility_id="utility-a",
        page_or_row="page:1",
        content="Unclassified source text.",
    )
    extractor = ExtractorAgent(
        FailingClient(), model="remote-model", provider="remote-provider"
    )

    with pytest.raises(RestrictedSourceError, match="explicitly PUBLIC"):
        extractor.extract(chunk)


def test_accepted_asus_fixture_matches_authoritative_contract() -> None:
    fixture_path = Path(__file__).parents[1] / "fixtures" / "accepted_project_version.json"
    version = AcceptedProjectVersion.model_validate_json(fixture_path.read_text())

    assert version.candidate.version_state.value == "STARTER_DATA"
    assert version.candidate.schedule.type is ScheduleType.IN_SERVICE_MILESTONE


def test_field_level_eval_separates_hallucinations() -> None:
    categories = [
        categorize_field(expected=230, actual=230, source_supported=True),
        categorize_field(expected="DESC", actual="Dominion", source_supported=True, normalization_equivalent=True),
        categorize_field(expected="Okatie", actual="Northgate", source_supported=False),
    ]

    metrics = evaluate_field_categories(
        categories,
        schema_valid_outputs=1,
        schema_invalid_outputs=0,
        evidence_associations=[True, False],
    )

    assert metrics.category_counts[FieldEvaluationCategory.CORRECT.value] == 1
    assert metrics.category_counts[FieldEvaluationCategory.UNSUPPORTED_HALLUCINATION.value] == 1
    assert metrics.evidence_association_accuracy == 0.5
