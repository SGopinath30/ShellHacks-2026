"""Authoritative contracts shared by extraction, Dell, and ASUS integration."""

from __future__ import annotations

import datetime as dt
from enum import StrEnum
from typing import Any, Generic, Self, TypeVar

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class SourceAccess(StrEnum):
    PUBLIC = "PUBLIC"
    CEII = "CEII"
    UNKNOWN = "UNKNOWN"


class SourceType(StrEnum):
    STARTER_WORKBOOK = "STARTER_WORKBOOK"
    CSV = "CSV"
    JSON = "JSON"
    PDF = "PDF"
    DOCX = "DOCX"
    WEB_PAGE = "WEB_PAGE"
    REGULATORY_FILING = "REGULATORY_FILING"
    GIS = "GIS"


class VerificationState(StrEnum):
    UNVERIFIED = "UNVERIFIED"
    VERIFIED_RULE = "VERIFIED_RULE"
    VERIFIED_HUMAN = "VERIFIED_HUMAN"
    UNRESOLVED = "UNRESOLVED"
    REJECTED = "REJECTED"


class AssociationState(StrEnum):
    ASSOCIATION_VERIFIED = "ASSOCIATION_VERIFIED"
    ASSOCIATION_AMBIGUOUS = "ASSOCIATION_AMBIGUOUS"
    ASSOCIATION_FAILED = "ASSOCIATION_FAILED"


class ExtractionMethod(StrEnum):
    TABLE_PARSER = "TABLE_PARSER"
    STRUCTURED_PARSER = "STRUCTURED_PARSER"
    TEXT_RULE = "TEXT_RULE"
    MODEL_EXTRACTION = "MODEL_EXTRACTION"
    HUMAN_CORRECTION = "HUMAN_CORRECTION"


class CanonicalProjectStatus(StrEnum):
    PROPOSED = "PROPOSED"
    PLANNED = "PLANNED"
    APPROVED = "APPROVED"
    IN_PROGRESS = "IN_PROGRESS"
    DELAYED = "DELAYED"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"
    RETIRED = "RETIRED"
    UNKNOWN = "UNKNOWN"


class ProjectType(StrEnum):
    TRANSMISSION_LINE = "TRANSMISSION_LINE"
    SUBSTATION = "SUBSTATION"
    RECONDUCTORING = "RECONDUCTORING"
    TRANSFORMER = "TRANSFORMER"
    DISTRIBUTION = "DISTRIBUTION"
    GENERATION = "GENERATION"
    OTHER = "OTHER"
    UNKNOWN = "UNKNOWN"


class DatePrecision(StrEnum):
    EXACT = "EXACT"
    MONTH = "MONTH"
    QUARTER = "QUARTER"
    SEASON = "SEASON"
    YEAR = "YEAR"
    UNKNOWN = "UNKNOWN"


class ScheduleType(StrEnum):
    CONSTRUCTION_WINDOW = "CONSTRUCTION_WINDOW"
    CONSTRUCTION_START_ONLY = "CONSTRUCTION_START_ONLY"
    CONSTRUCTION_END_ONLY = "CONSTRUCTION_END_ONLY"
    IN_SERVICE_MILESTONE = "IN_SERVICE_MILESTONE"
    NEED_DATE_MILESTONE = "NEED_DATE_MILESTONE"
    UNKNOWN = "UNKNOWN"


class ScheduleValidationOutcome(StrEnum):
    VALID = "VALID"
    PARTIALLY_FEASIBLE = "PARTIALLY_FEASIBLE"
    INVALID = "INVALID"


class GeometryOrigin(StrEnum):
    OPENSTREETMAP = "OPENSTREETMAP"
    UTILITY_GIS = "UTILITY_GIS"
    OPEN_INFRASTRUCTURE_MAP = "OPEN_INFRASTRUCTURE_MAP"
    RTO_ISO = "RTO_ISO"
    TWO_ENDPOINT_SEGMENT = "TWO_ENDPOINT_SEGMENT"
    OTHER = "OTHER"


class GeometryAssociationStatus(StrEnum):
    ACCEPTED = "ACCEPTED"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    UNRESOLVED = "UNRESOLVED"
    REJECTED = "REJECTED"


class GeometryQuality(StrEnum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    APPROXIMATE = "APPROXIMATE"
    UNKNOWN = "UNKNOWN"


class VersionState(StrEnum):
    STARTER_DATA = "STARTER_DATA"
    CANDIDATE = "CANDIDATE"
    CURRENT_VERIFIED = "CURRENT_VERIFIED"
    SUPERSEDED = "SUPERSEDED"


class ReconciliationDecision(StrEnum):
    SAME_PROJECT = "SAME_PROJECT"
    LIKELY_SAME_PROJECT = "LIKELY_SAME_PROJECT"
    DIFFERENT_PROJECT = "DIFFERENT_PROJECT"
    NEEDS_REVIEW = "NEEDS_REVIEW"


class VersionComparison(StrEnum):
    UNCHANGED = "UNCHANGED"
    UPDATED = "UPDATED"
    UNRESOLVED = "UNRESOLVED"


class ProjectValidationOutcome(StrEnum):
    ACCEPTED = "ACCEPTED"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    REJECTED = "REJECTED"


class EvidenceLocator(StrictModel):
    page: int | None = Field(default=None, ge=1)
    table: str | None = None
    sheet: str | None = None
    row: int | None = Field(default=None, ge=1)
    column: str | None = None
    element_id: str | None = None
    provider_feature_id: str | None = None


class FieldEvidence(StrictModel):
    evidence_id: str = Field(min_length=1)
    field_path: str = Field(min_length=1)
    source_version_id: str = Field(min_length=1)
    locator: EvidenceLocator
    original_text: str = Field(min_length=1)
    normalized_value: Any = None
    extraction_method: ExtractionMethod
    validation_state: VerificationState
    association_state: AssociationState


ValueT = TypeVar("ValueT")


class EvidenceValue(StrictModel, Generic[ValueT]):
    value: ValueT | None = None
    raw: str | None = None
    state: VerificationState = VerificationState.UNVERIFIED
    evidence_ids: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def verified_values_require_evidence(self) -> Self:
        if self.value is not None and not self.evidence_ids:
            raise ValueError("populated values must reference evidence")
        if self.value is None and self.state in {
            VerificationState.VERIFIED_RULE,
            VerificationState.VERIFIED_HUMAN,
        }:
            raise ValueError("a null value cannot be verified")
        return self


class DateRange(StrictModel):
    earliest: dt.date
    latest: dt.date

    @model_validator(mode="after")
    def ordered(self) -> Self:
        if self.latest < self.earliest:
            raise ValueError("latest date must not precede earliest date")
        return self


class Schedule(StrictModel):
    type: ScheduleType
    raw: str | None = None
    date: dt.date | None = None
    precision: DatePrecision = DatePrecision.UNKNOWN
    range: DateRange | None = None
    start: DateRange | None = None
    end: DateRange | None = None
    validation: ScheduleValidationOutcome = ScheduleValidationOutcome.VALID
    state: VerificationState = VerificationState.UNVERIFIED
    evidence_ids: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def coherent_schedule(self) -> Self:
        if self.date and self.range:
            raise ValueError("schedule cannot contain both date and range")
        if self.type is ScheduleType.CONSTRUCTION_WINDOW:
            if self.start is None or self.end is None:
                raise ValueError("construction windows require start and end ranges")
            if self.start.earliest > self.end.latest:
                self.validation = ScheduleValidationOutcome.INVALID
            elif self.start.latest > self.end.earliest:
                self.validation = ScheduleValidationOutcome.PARTIALLY_FEASIBLE
        if self.state in {
            VerificationState.VERIFIED_RULE,
            VerificationState.VERIFIED_HUMAN,
        } and not self.evidence_ids:
            raise ValueError("verified schedules must reference evidence")
        return self


class SourceArtifact(StrictModel):
    source_version_id: str = Field(min_length=1)
    source_type: SourceType
    utility: str = Field(min_length=1)
    path: str = Field(min_length=1)
    source_url: str | None = None
    downloaded_file_hash: str | None = None
    parser_version: str = "project-intelligence-1.0.0"
    source_access: SourceAccess = SourceAccess.UNKNOWN
    metadata: dict[str, Any] = Field(default_factory=dict)


class GeometryCandidate(StrictModel):
    candidate_geometry_id: str = Field(min_length=1)
    project_candidate_id: str | None = None
    geojson: dict[str, Any]
    candidate_feature_name: str | None = None
    provider: GeometryOrigin
    provider_feature_id: str | None = None
    discovery_method: str = Field(min_length=1)
    quality: GeometryQuality = GeometryQuality.UNKNOWN
    operator: str | None = None
    state: str | None = None
    county: str | None = None
    voltage_kv: float | None = Field(default=None, gt=0, le=2_000)

    @model_validator(mode="after")
    def supported_geojson(self) -> Self:
        geometry_type = self.geojson.get("type")
        if geometry_type not in {"Point", "LineString", "MultiLineString", "Polygon"}:
            raise ValueError("unsupported GeoJSON geometry type")
        if "coordinates" not in self.geojson:
            raise ValueError("GeoJSON coordinates are required")
        return self


class GeometryValidation(StrictModel):
    candidate_geometry_id: str
    status: GeometryAssociationStatus
    origin: GeometryOrigin
    quality: GeometryQuality
    reasons: list[str] = Field(min_length=1)
    validation_state: VerificationState


class CandidateProject(StrictModel):
    candidate_project_id: str = Field(min_length=1)
    source_version_id: str = Field(min_length=1)
    supporting_source_version_ids: list[str] = Field(default_factory=list)
    source_access: SourceAccess = SourceAccess.UNKNOWN
    utility_id: str = Field(min_length=1)
    utility_id_evidence_ids: list[str] = Field(min_length=1)
    starter_project_id: str | None = None
    starter_project_id_evidence_ids: list[str] = Field(default_factory=list)
    external_project_id: str | None = None
    external_project_id_evidence_ids: list[str] = Field(default_factory=list)
    name: EvidenceValue[str]
    description: EvidenceValue[str] | None = None
    voltage_kv: EvidenceValue[float] | None = None
    status: EvidenceValue[CanonicalProjectStatus] | None = None
    project_type: EvidenceValue[ProjectType] | None = None
    schedule: Schedule | None = None
    endpoints: list[EvidenceValue[str]] = Field(default_factory=list)
    state: EvidenceValue[str] | None = None
    county: EvidenceValue[str] | None = None
    geometry_candidate: GeometryCandidate | None = None
    geometry_validation: GeometryValidation | None = None
    field_evidence: list[FieldEvidence] = Field(default_factory=list)
    version_state: VersionState = VersionState.CANDIDATE

    @model_validator(mode="after")
    def evidence_references_exist(self) -> Self:
        available = {item.evidence_id for item in self.field_evidence}
        if len(available) != len(self.field_evidence):
            raise ValueError("field evidence IDs must be unique")
        allowed_sources = {
            self.source_version_id,
            *self.supporting_source_version_ids,
        }
        if any(
            item.source_version_id not in allowed_sources
            for item in self.field_evidence
        ):
            raise ValueError(
                "field evidence must use a registered candidate source version"
            )
        referenced = set(self.name.evidence_ids)
        referenced.update(self.utility_id_evidence_ids)
        referenced.update(self.starter_project_id_evidence_ids)
        referenced.update(self.external_project_id_evidence_ids)
        for value in (
            self.description,
            self.voltage_kv,
            self.status,
            self.project_type,
            self.state,
            self.county,
        ):
            if value:
                referenced.update(value.evidence_ids)
        for endpoint in self.endpoints:
            referenced.update(endpoint.evidence_ids)
        if self.schedule:
            referenced.update(self.schedule.evidence_ids)
        missing = referenced - available
        if missing:
            raise ValueError(f"candidate references missing evidence: {sorted(missing)}")
        if self.external_project_id and not self.external_project_id_evidence_ids:
            raise ValueError("external project IDs must reference evidence")
        if self.starter_project_id and not self.starter_project_id_evidence_ids:
            raise ValueError("starter project IDs must reference evidence")
        if (
            self.geometry_candidate
            and self.geometry_candidate.project_candidate_id
            and self.geometry_candidate.project_candidate_id != self.candidate_project_id
        ):
            raise ValueError("geometry candidate is linked to a different project")
        if self.geometry_validation and not self.geometry_candidate:
            raise ValueError("geometry validation requires a geometry candidate")
        if (
            self.geometry_validation
            and self.geometry_candidate
            and self.geometry_validation.candidate_geometry_id
            != self.geometry_candidate.candidate_geometry_id
        ):
            raise ValueError("geometry validation is linked to a different geometry")
        return self


class ProjectValidationIssue(StrictModel):
    code: str = Field(min_length=1)
    message: str = Field(min_length=1)
    field_path: str | None = None
    state: VerificationState


class ProjectValidationResult(StrictModel):
    candidate_project_id: str = Field(min_length=1)
    outcome: ProjectValidationOutcome
    field_states: dict[str, VerificationState] = Field(default_factory=dict)
    issues: list[ProjectValidationIssue] = Field(default_factory=list)
    ready_for_asus: bool = False

    @model_validator(mode="after")
    def readiness_matches_outcome(self) -> Self:
        if self.ready_for_asus != (
            self.outcome is ProjectValidationOutcome.ACCEPTED
        ):
            raise ValueError("ready_for_asus must match an ACCEPTED outcome")
        return self


class AcceptedProjectVersion(StrictModel):
    project_version_id: str = Field(min_length=1)
    project_identity: str = Field(min_length=1)
    candidate: CandidateProject
    validation: ProjectValidationResult
    accepted_at: dt.datetime = Field(
        default_factory=lambda: dt.datetime.now(dt.timezone.utc)
    )
    accepted_by: str = Field(min_length=1)
    previous_version_id: str | None = None

    @model_validator(mode="after")
    def accepted_name_is_verified(self) -> Self:
        if self.candidate.source_access is not SourceAccess.PUBLIC:
            raise ValueError("only confirmed public sources can become project versions")
        if self.candidate.name.state not in {
            VerificationState.VERIFIED_RULE,
            VerificationState.VERIFIED_HUMAN,
        }:
            raise ValueError("accepted project names must be verified")
        if self.validation.candidate_project_id != self.candidate.candidate_project_id:
            raise ValueError("validation must reference the accepted candidate")
        if self.validation.outcome is not ProjectValidationOutcome.ACCEPTED:
            raise ValueError("only accepted candidates can become project versions")
        return self


class ProjectReconciliationProposal(StrictModel):
    left_candidate_id: str
    right_candidate_id: str
    decision: ReconciliationDecision
    reasons: list[str] = Field(min_length=1)
    requires_human_review: bool = True
    approved: bool = False


class VersionComparisonResult(StrictModel):
    result: VersionComparison
    changed_fields: list[str] = Field(default_factory=list)
    unresolved_fields: list[str] = Field(default_factory=list)
