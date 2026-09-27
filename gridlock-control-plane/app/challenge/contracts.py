"""Canonical versioned import contract; the old API remains available."""
from datetime import date
from enum import Enum
from typing import Annotated, Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


Lon = Annotated[float, Field(ge=-180, le=180)]
Lat = Annotated[float, Field(ge=-90, le=90)]
Coordinate = tuple[Lon, Lat]


class Point(Strict):
    type: Literal["Point"] = "Point"
    coordinates: Coordinate


class Line(Strict):
    type: Literal["LineString"] = "LineString"
    coordinates: list[Coordinate] = Field(min_length=2)

    @model_validator(mode="after")
    def distinct(self):
        if len(set(self.coordinates)) < 2:
            raise ValueError("A line needs at least two distinct points")
        return self


Geometry = Annotated[Point | Line, Field(discriminator="type")]


class Quality(str, Enum):
    AUTHORITATIVE = "AUTHORITATIVE"
    HIGH = "HIGH"
    APPROXIMATE = "APPROXIMATE"
    UNRESOLVED = "UNRESOLVED"


class Validation(str, Enum):
    ACCEPTED = "ACCEPTED"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    UNRESOLVED = "UNRESOLVED"


class Bounds(Strict):
    earliest: date
    latest: date

    @model_validator(mode="after")
    def ordered(self):
        if self.earliest > self.latest:
            raise ValueError("earliest must be <= latest")
        return self


class Construction(Strict):
    type: Literal["CONSTRUCTION_WINDOW"] = "CONSTRUCTION_WINDOW"
    start: Bounds
    end_exclusive: Bounds

    @model_validator(mode="after")
    def feasible(self):
        if self.start.earliest >= self.end_exclusive.latest:
            raise ValueError("Construction window cannot have positive duration")
        return self


class Milestone(Strict):
    type: Literal["IN_SERVICE_GAP"] = "IN_SERVICE_GAP"
    in_service_date: date


class Unknown(Strict):
    type: Literal["UNKNOWN"] = "UNKNOWN"


Schedule = Annotated[Construction | Milestone | Unknown, Field(discriminator="type")]


class Evidence(Strict):
    source_id: str = Field(min_length=1)
    source_name: str = Field(min_length=1)
    page_or_row: str | None = None
    snippet: str | None = None
    source_url: str | None = None


class ProjectInput(Strict):
    project_id: str = Field(min_length=1)
    utility_id: str = Field(min_length=1)
    project_name: str = Field(min_length=1)
    project_type: Literal["transmission_line", "substation", "rebuild", "upgrade", "other"]
    status: Literal["proposed", "planned", "approved", "in_progress", "under_construction", "on_hold", "cancelled", "completed", "operational", "unknown"] = "unknown"
    voltage_kv: float | None = Field(None, gt=0)
    location_text: str = Field(min_length=1)
    geometry: Geometry | None = None
    center_point: Point | None = None
    geometry_origin: Literal["UTILITY_GIS", "PUBLIC_GIS", "OSM_MATCH", "TWO_ENDPOINT_SEGMENT", "SINGLE_LOCATED_POINT", "CENTER_POINT", "MANUAL_VERIFIED"]
    geometry_quality: Quality
    validation_state: Validation
    source_crs: Literal["EPSG:4326"] = "EPSG:4326"
    schedule: Schedule = Field(default_factory=Unknown)
    evidence: list[Evidence] = Field(min_length=1)
    source_version_ids: list[str] = Field(default_factory=list)
    upstream_project_version_id: str | None = None
    upstream_candidate_id: str | None = None
    is_fixture: bool = False
    extraction_confidence: float | None = Field(None, ge=0, le=1)
    extraction_model: str | None = None
    extraction_model_version: str | None = None

    @model_validator(mode="after")
    def consistent(self):
        if self.geometry_origin == "TWO_ENDPOINT_SEGMENT" and self.geometry:
            if not isinstance(self.geometry, Line) or len(self.geometry.coordinates) != 2:
                raise ValueError("An endpoint segment requires a two-point line")
            if self.geometry_quality not in (Quality.APPROXIMATE, Quality.UNRESOLVED):
                raise ValueError("An endpoint segment is an approximate route")
        if self.extraction_model and self.extraction_confidence is None:
            raise ValueError("AI extraction needs confidence metadata")
        return self


class ProjectVersion(ProjectInput):
    version_id: str
    version_number: int


def geometry_status(p):
    if p.geometry is None or p.geometry_quality == Quality.UNRESOLVED or p.validation_state == Validation.UNRESOLVED:
        return "UNAVAILABLE"
    if p.geometry_quality == Quality.APPROXIMATE or p.validation_state == Validation.NEEDS_REVIEW:
        return "APPROXIMATE"
    return "CALCULABLE"
