"""Pydantic contracts for the extraction boundary.

The ingestion team hands :class:`DocumentChunk` objects to this subsystem.  The
control plane should persist only validated :class:`ProjectRecord` objects.
Candidate models deliberately allow missing values so that the model can say
"unknown" rather than fabricate required output.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from enum import StrEnum
from typing import Any, Optional, Self

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, model_validator
from pydantic.json_schema import SkipJsonSchema

from project_intelligence.contracts import SourceAccess


class StrictModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        populate_by_name=True,
        str_strip_whitespace=True,
    )


class ProjectType(StrEnum):
    TRANSMISSION_LINE = "transmission_line"
    SUBSTATION = "substation"
    RECONDUCTORING = "reconductoring"
    TRANSFORMER = "transformer"
    DISTRIBUTION = "distribution"
    GENERATION = "generation"
    OTHER = "other"
    UNKNOWN = "unknown"


class ProjectStatus(StrEnum):
    PROPOSED = "proposed"
    PLANNED = "planned"
    APPROVED = "approved"
    IN_PROGRESS = "in_progress"
    DELAYED = "delayed"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    RETIRED = "retired"
    UNKNOWN = "unknown"


class DatePrecision(StrEnum):
    EXACT = "exact"
    MONTH = "month"
    QUARTER = "quarter"
    SEASON = "season"
    YEAR = "year"
    UNKNOWN = "unknown"


class ValidationOutcome(StrEnum):
    PASS = "PASS"
    CORRECTED = "CORRECTED"
    UNRESOLVED = "UNRESOLVED"


class IssueSeverity(StrEnum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


class DocumentChunk(StrictModel):
    """A text/table fragment produced by the ingestion subsystem."""

    source_id: str = Field(min_length=1)
    source_name: str = Field(min_length=1)
    utility_id: str = Field(min_length=1)
    page_or_row: str = Field(min_length=1)
    content: str = Field(min_length=1)
    source_url: HttpUrl | None = None
    document_hash: str | None = None
    source_access: SourceAccess = SourceAccess.UNKNOWN
    metadata: dict[str, Any] = Field(default_factory=dict)


class SourceEvidence(StrictModel):
    source_id: str = Field(min_length=1)
    source_name: str = Field(min_length=1)
    page_or_row: str = Field(min_length=1)
    snippet: str = Field(min_length=1, max_length=2_000)
    source_url: HttpUrl | None = None
    document_hash: str | None = None


class FieldEvidence(StrictModel):
    field_name: str = Field(min_length=1)
    quoted_text: str = Field(min_length=1, max_length=1_000)
    page_or_row: SkipJsonSchema[Optional[str]] = None


class GeometryCandidate(StrictModel):
    """GeoJSON supplied by a locator; never inferred by the extractor."""

    geojson: dict[str, Any]
    confidence: float = Field(ge=0, le=1)
    is_approximate: bool = True
    method: str = Field(min_length=1)

    @model_validator(mode="after")
    def supported_geojson(self) -> Self:
        geometry_type = self.geojson.get("type")
        if geometry_type not in {"Point", "LineString", "MultiLineString"}:
            raise ValueError("geometry must be Point, LineString, or MultiLineString GeoJSON")
        if "coordinates" not in self.geojson:
            raise ValueError("geometry GeoJSON must contain coordinates")
        return self


class ExtractionAudit(StrictModel):
    model: str = Field(min_length=1)
    model_version: str | None = None
    provider: str = Field(min_length=1)
    extracted_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    prompt_version: str = Field(min_length=1)


class ExtractionManifest(StrictModel):
    """Diagnostic provenance for one model extraction request."""

    run_id: str = Field(min_length=1)
    source_id: str = Field(min_length=1)
    source_url: HttpUrl | None = None
    downloaded_file_hash: str | None = None
    parser_version: str = Field(min_length=1)
    parsed_element_count: int = Field(ge=1)
    selected_page_or_row_ids: list[str] = Field(min_length=1)
    input_content_hash: str = Field(min_length=1)
    model_id: str = Field(min_length=1)
    prompt_version: str = Field(min_length=1)
    schema_version: str = Field(min_length=1)
    cache_hit: bool = False
    mock_mode: bool = False


class CandidateProject(StrictModel):
    """Potential project returned by an LLM before trustworthy validation."""

    project_name: str = Field(alias="name", min_length=1)
    source_snippet: str = Field(alias="description", min_length=1, max_length=2_000)
    status: ProjectStatus
    project_id: SkipJsonSchema[Optional[str]] = None
    source_project_id: SkipJsonSchema[Optional[str]] = None
    utility_id: SkipJsonSchema[Optional[str]] = None
    project_type: ProjectType = ProjectType.UNKNOWN
    voltage_kv: float | None = Field(default=None, gt=0, le=2_000)
    start_date: date | None = None
    end_date: date | None = None
    start_date_precision: DatePrecision = DatePrecision.UNKNOWN
    end_date_precision: DatePrecision = DatePrecision.UNKNOWN
    start_date_text: str | None = None
    end_date_text: str | None = None
    geometry: SkipJsonSchema[Optional[Any]] = None
    location_text: str | None = None
    source_id: SkipJsonSchema[Optional[str]] = None
    source_page_row: SkipJsonSchema[Optional[str]] = None
    field_evidence: list[FieldEvidence] | None = None
    extraction_confidence: float = Field(default=0.0, ge=0, le=1)

    @model_validator(mode="after")
    def coherent_dates(self) -> Self:
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValueError("end_date must not precede start_date")
        return self


class ExtractionBatch(StrictModel):
    projects: list[CandidateProject] = Field(default_factory=list)
    audit: ExtractionAudit
    manifest: ExtractionManifest


class CandidateProjectBatch(StrictModel):
    """Model-facing payload; runtime audit metadata is attached by our code."""

    projects: list[CandidateProject] = Field(..., min_length=1)


class ProjectRecord(StrictModel):
    """Stable cross-team contract emitted only after validation."""

    project_id: str = Field(min_length=1)
    utility_id: str = Field(min_length=1)
    project_name: str = Field(min_length=1)
    project_type: ProjectType
    voltage_kv: float | None = Field(default=None, gt=0, le=2_000)
    start_date: date | None = None
    end_date: date | None = None
    start_date_precision: DatePrecision = DatePrecision.UNKNOWN
    end_date_precision: DatePrecision = DatePrecision.UNKNOWN
    start_date_text: str | None = None
    end_date_text: str | None = None
    status: ProjectStatus
    geometry: GeometryCandidate | None = None
    location_text: str | None = Field(default=None, min_length=1)
    source_id: str = Field(min_length=1)
    source_page_row: str = Field(min_length=1)
    source_snippet: str | None = Field(default=None, max_length=2_000)
    evidence: list[SourceEvidence] = Field(min_length=1)
    extraction_confidence: float = Field(ge=0, le=1)
    audit: ExtractionAudit

    @model_validator(mode="after")
    def coherent_record(self) -> Self:
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValueError("end_date must not precede start_date")
        if not any(item.source_id == self.source_id for item in self.evidence):
            raise ValueError("evidence must include the record source_id")
        return self


class ValidationIssue(StrictModel):
    code: str = Field(min_length=1)
    message: str = Field(min_length=1)
    severity: IssueSeverity
    field: str | None = None


class ValidationResult(StrictModel):
    outcome: ValidationOutcome
    candidate: CandidateProject
    record: ProjectRecord | None = None
    issues: list[ValidationIssue] = Field(default_factory=list)
    corrections: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def outcome_matches_record(self) -> Self:
        if self.outcome is ValidationOutcome.UNRESOLVED and self.record is not None:
            raise ValueError("UNRESOLVED results must not contain a ProjectRecord")
        if self.outcome is not ValidationOutcome.UNRESOLVED and self.record is None:
            raise ValueError("PASS/CORRECTED results must contain a ProjectRecord")
        return self


class ValidatorDecision(StrictModel):
    """Model-facing validator response before a trusted record is assembled."""

    outcome: ValidationOutcome
    candidate: CandidateProject
    issues: list[ValidationIssue] = Field(default_factory=list)
    corrections: dict[str, Any] = Field(default_factory=dict)


class ExtractionRun(StrictModel):
    """Aggregate result returned by the extraction swarm."""

    chunks_processed: int = Field(ge=0)
    candidates_found: int = Field(ge=0)
    results: list[ValidationResult] = Field(default_factory=list)
    manifests: list[ExtractionManifest] = Field(default_factory=list)
