from extraction.models import (
    CandidateProject,
    DocumentChunk,
    ExtractionAudit,
    FieldEvidence,
    ProjectStatus,
    ProjectType,
    ValidationOutcome,
)
from agents.validator import ValidatorAgent, validate_record_deterministically


def _chunk() -> DocumentChunk:
    return DocumentChunk(
        source_id="source-a",
        source_name="plan.txt",
        utility_id="utility-a",
        page_or_row="page:1",
        content="North Ridge Substation is planned in North Ridge.",
    )


def _audit() -> ExtractionAudit:
    return ExtractionAudit(model="fake", provider="test", prompt_version="test-v1")


def test_deterministic_validation_accepts_verbatim_text() -> None:
    assert validate_record_deterministically(
        {
            "name": "North Ridge Substation",
            "description": "North Ridge Substation is planned in North Ridge.",
            "status": "planned",
        },
        _chunk().content,
    )


def test_deterministic_validation_rejects_paraphrased_description() -> None:
    assert not validate_record_deterministically(
        {
            "name": "North Ridge Substation",
            "description": "A new substation will be constructed in North Ridge.",
            "status": "planned",
        },
        _chunk().content,
    )


def test_deterministic_validation_rejects_noncanonical_status() -> None:
    assert not validate_record_deterministically(
        {
            "name": "North Ridge Substation",
            "description": "North Ridge Substation is planned in North Ridge.",
            "status": "unknown",
        },
        _chunk().content,
    )


def test_validator_accepts_three_field_candidate() -> None:
    candidate = CandidateProject(
        name="North Ridge Substation",
        description="North Ridge Substation is planned in North Ridge.",
        status=ProjectStatus.PLANNED,
    )

    result = ValidatorAgent().validate(_chunk(), candidate, _audit())

    assert result.outcome is ValidationOutcome.CORRECTED
    assert result.record is not None
    assert result.record.location_text is None
    assert result.candidate.field_evidence is None


def test_validator_builds_record_and_corrects_authoritative_metadata() -> None:
    candidate = CandidateProject(
        utility_id="wrong-utility",
        project_name="North Ridge Substation",
        project_type=ProjectType.SUBSTATION,
        status=ProjectStatus.PLANNED,
        location_text="North Ridge",
        source_id="wrong-source",
        source_page_row="wrong-page",
        source_snippet="North Ridge Substation is planned in North Ridge.",
        field_evidence=[
            FieldEvidence(
                field_name="project_name",
                quoted_text="North Ridge Substation",
                page_or_row="page:1",
            ),
            FieldEvidence(
                field_name="project_type",
                quoted_text="Substation",
                page_or_row="page:1",
            ),
            FieldEvidence(
                field_name="status",
                quoted_text="planned",
                page_or_row="page:1",
            ),
            FieldEvidence(
                field_name="location_text",
                quoted_text="North Ridge",
                page_or_row="page:1",
            ),
        ],
        extraction_confidence=0.9,
    )

    result = ValidatorAgent().validate(_chunk(), candidate, _audit())

    assert result.outcome is ValidationOutcome.CORRECTED
    assert result.record is not None
    assert result.record.utility_id == "utility-a"
    assert result.record.source_id == "source-a"
    assert result.record.project_id.startswith("project-")


def test_validator_rejects_candidate_without_verbatim_evidence() -> None:
    candidate = CandidateProject(
        project_name="North Ridge Substation",
        status=ProjectStatus.UNKNOWN,
        location_text="North Ridge",
        source_snippet="This sentence was invented.",
        extraction_confidence=0.9,
    )

    result = ValidatorAgent().validate(_chunk(), candidate, _audit())

    assert result.outcome is ValidationOutcome.UNRESOLVED
    assert result.record is None
    assert any(issue.code == "evidence_missing" for issue in result.issues)


def test_validator_rejects_example_values_absent_from_source() -> None:
    candidate = CandidateProject(
        utility_id="utility-a",
        project_name="East Junction Substation Project",
        project_type=ProjectType.SUBSTATION,
        status=ProjectStatus.APPROVED,
        location_text="East Junction",
        source_id="source-a",
        source_page_row="page:1",
        source_snippet="East Junction Substation Project",
        field_evidence=[
            FieldEvidence(
                field_name="project_name",
                quoted_text="East Junction Substation Project",
                page_or_row="page:1",
            )
        ],
        extraction_confidence=0.99,
    )

    result = ValidatorAgent().validate(_chunk(), candidate, _audit())

    assert result.outcome is ValidationOutcome.UNRESOLVED
    assert result.record is None
    assert any(issue.code == "evidence_missing" for issue in result.issues)


def test_validator_rejects_date_evidence_with_wrong_meaning() -> None:
    chunk = _chunk().model_copy(
        update={"content": "North Ridge Substation has an in-service date of 2028."}
    )
    candidate = CandidateProject(
        utility_id="utility-a",
        project_name="North Ridge Substation",
        status=ProjectStatus.UNKNOWN,
        start_date_text="2028",
        location_text="North Ridge",
        source_id="source-a",
        source_page_row="page:1",
        source_snippet="North Ridge Substation has an in-service date of 2028.",
        field_evidence=[
            FieldEvidence(
                field_name="project_name",
                quoted_text="North Ridge Substation",
                page_or_row="page:1",
            ),
            FieldEvidence(
                field_name="start_date",
                quoted_text="in-service date of 2028",
                page_or_row="page:1",
            ),
            FieldEvidence(
                field_name="location_text",
                quoted_text="North Ridge",
                page_or_row="page:1",
            ),
        ],
        extraction_confidence=0.8,
    )

    result = ValidatorAgent().validate(chunk, candidate, _audit())

    assert result.outcome is ValidationOutcome.UNRESOLVED
    assert any(issue.code == "field_evidence_mismatch" for issue in result.issues)
