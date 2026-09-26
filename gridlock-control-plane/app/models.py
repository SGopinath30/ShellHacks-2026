"""
Shared contracts for GridLock.

These models are the frozen interface between subsystems:
- Extraction (M4 Mac) produces ProjectRecord + SourceEvidence
- Ingestion (Dell) produces raw Source records that feed extraction
- Control Plane (this machine) computes MatchResult from ProjectRecords
- Frontend (Lenovo) consumes /projects and /matches

Do not change field names/types without team agreement (PRD section 26).
"""

from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, field_validator


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class ProjectType(str, Enum):
    TRANSMISSION_LINE = "transmission_line"
    SUBSTATION = "substation"
    REBUILD = "rebuild"
    UPGRADE = "upgrade"
    OTHER = "other"


class ProjectStatus(str, Enum):
    PLANNED = "planned"
    APPROVED = "approved"
    UNDER_CONSTRUCTION = "under_construction"
    ON_HOLD = "on_hold"
    CANCELLED = "cancelled"
    UNKNOWN = "unknown"


class DatePrecision(str, Enum):
    """How precisely a date is known in the source document. Never fabricate
    precision the source doesn't have (PRD section 13)."""
    EXACT = "exact"          # 2028-04-01
    QUARTER = "quarter"      # Q2 2028
    YEAR = "year"            # 2028
    UNKNOWN = "unknown"


class ReasonCode(str, Enum):
    SPATIAL = "SPATIAL"
    TEMPORAL = "TEMPORAL"
    SEAM = "SEAM"
    SIMILAR_VOLTAGE = "SIMILAR_VOLTAGE"


class ReviewStatus(str, Enum):
    UNREVIEWED = "unreviewed"
    INVESTIGATE = "investigate"
    DISMISS = "dismiss"
    CONTACT_UTILITY = "contact_utility"


class ExtractionValidation(str, Enum):
    PASS = "PASS"
    CORRECTED = "CORRECTED"
    UNRESOLVED = "UNRESOLVED"


# ---------------------------------------------------------------------------
# Source evidence / provenance
# ---------------------------------------------------------------------------

class SourceEvidence(BaseModel):
    """Every extracted fact must be traceable back to this."""

    source_id: str = Field(..., description="ID of the originating document/dataset")
    source_name: str = Field(..., description="Human-readable source name, e.g. 'Georgia Utility Plan 2026'")
    page_or_row: Optional[str] = Field(None, description="e.g. 'page 84', 'row 17', 'GIS feature 402'")
    snippet: Optional[str] = Field(None, description="Original text/cell the value was extracted from")
    source_url: Optional[str] = None


# ---------------------------------------------------------------------------
# Project geometry (kept intentionally simple; GeoJSON-compatible)
# ---------------------------------------------------------------------------

class PointGeometry(BaseModel):
    type: str = Field(default="Point", frozen=True)
    coordinates: tuple[float, float]  # (lon, lat)


class LineGeometry(BaseModel):
    type: str = Field(default="LineString", frozen=True)
    coordinates: list[tuple[float, float]]  # [(lon, lat), ...]


Geometry = PointGeometry | LineGeometry


# ---------------------------------------------------------------------------
# Core project record
# ---------------------------------------------------------------------------

class ProjectRecord(BaseModel):
    project_id: str
    utility_id: str
    project_name: str
    project_type: ProjectType
    voltage_kv: Optional[float] = None

    start_date: Optional[date] = None
    end_date: Optional[date] = None
    start_date_precision: DatePrecision = DatePrecision.UNKNOWN
    end_date_precision: DatePrecision = DatePrecision.UNKNOWN

    status: ProjectStatus = ProjectStatus.UNKNOWN

    geometry: Optional[Geometry] = None
    geometry_is_approximate: bool = False

    location_text: str = Field(..., description="Original, unaltered location description from the source")

    evidence: SourceEvidence

    extraction_confidence: Optional[float] = Field(
        None, ge=0.0, le=1.0, description="Required if this record came from AI extraction"
    )
    extraction_model: Optional[str] = None
    extraction_model_version: Optional[str] = None
    extracted_at: Optional[datetime] = None

    @field_validator("end_date")
    @classmethod
    def end_after_start(cls, v, info):
        start = info.data.get("start_date")
        if v is not None and start is not None and v < start:
            raise ValueError("end_date cannot be before start_date")
        return v


# ---------------------------------------------------------------------------
# Match result
# ---------------------------------------------------------------------------

class MatchResult(BaseModel):
    match_id: str
    project_a: str  # project_id
    project_b: str  # project_id

    distance_miles: Optional[float] = None
    overlap_days: Optional[int] = None
    near_boundary: bool = False
    boundary_distance_miles: Optional[float] = None

    reason_codes: list[ReasonCode] = Field(default_factory=list)

    spatial_threshold_miles: Optional[float] = None
    temporal_threshold_days: Optional[int] = None

    source_complete: bool = True
    computed_at: datetime = Field(default_factory=datetime.utcnow)

    review_status: ReviewStatus = ReviewStatus.UNREVIEWED


class ReviewStateUpdate(BaseModel):
    review_status: ReviewStatus
    note: Optional[str] = None
    reviewed_by: Optional[str] = None


# ---------------------------------------------------------------------------
# API request bodies
# ---------------------------------------------------------------------------

class MatchRecomputeRequest(BaseModel):
    utility_ids: Optional[list[str]] = None
    spatial_threshold_miles: float = 25.0
    temporal_min_overlap_days: int = 90
    seam_buffer_miles: float = 20.0
    require_spatial_or_temporal: bool = True  # flag = spatial_match OR temporal_match
