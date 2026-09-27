"""Source-backed location review and qualified cross-utility pair discovery."""
from typing import Literal
from uuid import uuid4

from pydantic import Field, field_validator, model_validator
from psycopg.types.json import Jsonb

from . import repository
from .config import get_config
from .contracts import Evidence, Geometry, Line, ProjectInput, ProjectVersion, Quality, Strict, Validation, geometry_status


EligibleStatus = Literal["proposed", "planned", "approved", "in_progress", "under_construction",
                         "on_hold", "cancelled", "unknown"]
VerifiedOrigin = Literal["UTILITY_GIS", "PUBLIC_GIS", "OSM_MATCH", "SINGLE_LOCATED_POINT",
                         "MANUAL_VERIFIED", "TWO_ENDPOINT_SEGMENT"]


class LocationVerificationRequest(Strict):
    base_version_id: str = Field(min_length=1)
    actor_id: str = Field(min_length=1, max_length=200)
    actor_role: str = Field(min_length=1, max_length=200)
    reason: str = Field(min_length=1, max_length=4000)
    location_text: str = Field(min_length=1)
    geometry: Geometry
    geometry_origin: VerifiedOrigin
    geometry_quality: Literal[Quality.AUTHORITATIVE, Quality.HIGH, Quality.APPROXIMATE]
    geometry_evidence: Evidence
    status: EligibleStatus | None = None
    status_evidence: Evidence | None = None

    @field_validator("base_version_id", "actor_id", "actor_role", "reason", "location_text")
    @classmethod
    def nonblank(cls, value):
        if not value.strip():
            raise ValueError("Must contain visible text")
        return value.strip()

    @model_validator(mode="after")
    def source_backed(self):
        if self.geometry_origin == "TWO_ENDPOINT_SEGMENT" and (
            not isinstance(self.geometry,Line) or len(self.geometry.coordinates) != 2
            or self.geometry_quality != Quality.APPROXIMATE
        ):
            raise ValueError("A two-endpoint segment must be a two-point approximate line")
        for evidence in (self.geometry_evidence, self.status_evidence):
            if evidence is None:
                continue
            if not evidence.source_url or not evidence.source_url.startswith(("https://", "http://")):
                raise ValueError("Verification evidence needs a source URL")
            if not (evidence.page_or_row or evidence.snippet):
                raise ValueError("Verification evidence needs a page, feature ID, or supporting snippet")
        return self


def readiness(project,config=None):
    """Stricter than ordinary opportunities: only accepted, usable site geometry qualifies."""
    config = config or get_config()
    blockers = []
    if project.is_fixture:
        blockers.append("FIXTURE")
    if project.geometry is None:
        blockers.append("MISSING_GEOMETRY")
    elif project.geometry_quality == Quality.UNRESOLVED:
        blockers.append("UNRESOLVED_GEOMETRY")
    elif project.geometry_quality == Quality.APPROXIMATE:
        blockers.append("APPROXIMATE_GEOMETRY")
    if project.geometry_origin == "CENTER_POINT":
        blockers.append("REFERENCE_CENTER_POINT")
    if project.validation_state != Validation.ACCEPTED:
        blockers.append("VALIDATION_PENDING")
    if project.status not in config.eligible_statuses:
        blockers.append("STATUS_NOT_ELIGIBLE")
    if project.geometry is None:
        coordinate_role = "NONE"
    elif project.geometry_origin == "CENTER_POINT":
        coordinate_role = "REFERENCE_ONLY"
    elif geometry_status(project) == "UNAVAILABLE":
        coordinate_role = "UNVERIFIED_GEOMETRY"
    else:
        coordinate_role = "PROJECT_GEOMETRY"
    return {"qualified_ready": not blockers,
            "matching_eligible": (not project.is_fixture and project.status in config.eligible_statuses
                                  and geometry_status(project) != "UNAVAILABLE"),
            "blockers": blockers, "coordinate_role": coordinate_role}


def review_queue(projects,utility_id=None,include_fixtures=False):
    rows = []
    for project in projects:
        if utility_id and project.utility_id != utility_id:
            continue
        if project.is_fixture and not include_fixtures:
            continue
        state = readiness(project)
        if not state["qualified_ready"]:
            rows.append({"project": project.model_dump(mode="json"), **state})
    return {"total": len(rows), "projects": rows}


def assess_pair(a,b,meters,config=None):
    config = config or get_config()
    first,second = readiness(a,config),readiness(b,config)
    blockers = []
    if a.project_id == b.project_id:
        blockers.append("SAME_PROJECT")
    elif a.utility_id == b.utility_id:
        blockers.append("SAME_UTILITY")
    if first["blockers"]:
        blockers.append("PROJECT_A_NEEDS_REVIEW")
    if second["blockers"]:
        blockers.append("PROJECT_B_NEEDS_REVIEW")
    distance = None
    if meters is not None:
        reference = first["coordinate_role"] == "REFERENCE_ONLY" or second["coordinate_role"] == "REFERENCE_ONLY"
        kind = ("REFERENCE_POINT_SEPARATION" if reference else
                "PROJECT_GEOMETRY_DISTANCE" if first["qualified_ready"] and second["qualified_ready"]
                else "UNVERIFIED_GEOMETRY_SEPARATION")
        distance = {"meters": meters, "miles": meters/config.meters_per_mile, "kind": kind,
                    "within_configured_maximum": meters < config.maximum_meters}
    if not blockers:
        if distance is None:
            blockers.append("DISTANCE_UNAVAILABLE")
        elif meters >= config.maximum_meters:
            blockers.append("OUT_OF_RANGE")
    return {"project_a": {"project_id": a.project_id, **first},
            "project_b": {"project_id": b.project_id, **second},
            "distance": distance, "maximum_meters": config.maximum_meters,
            "strict_upper_bound": True, "blockers": blockers,
            "qualifies": not blockers}


def qualified_pairs(opportunities,utility_a="DESC",utility_b="GPC"):
    selected = []
    for item in opportunities:
        projects = [ProjectVersion.model_validate(p) for p in item["projects"]]
        if {p.utility_id for p in projects} != {utility_a,utility_b}:
            continue
        if all(readiness(p)["qualified_ready"] for p in projects):
            selected.append(item)
    return selected


def verify_location(project_id,request):
    with repository.connect() as conn:
        current = repository.current_project(conn,project_id,lock=True)
        if current is None:
            raise LookupError("Project not found")
        if current.version_id != request.base_version_id:
            raise ValueError("Project version changed; refresh before verifying")
        if current.is_fixture:
            raise ValueError("Starter fixtures cannot be verified through this workflow")
        if request.status is not None and request.status != current.status and request.status_evidence is None:
            raise ValueError("A status change needs separate source evidence")
        original = current.model_dump(mode="json",exclude={"version_id","version_number"})
        evidence = [e.model_dump(mode="json") for e in current.evidence]
        evidence.append(request.geometry_evidence.model_dump(mode="json"))
        if request.status_evidence is not None:
            evidence.append(request.status_evidence.model_dump(mode="json"))
        updated = {**original,
                   "location_text": request.location_text,
                   "geometry": request.geometry.model_dump(mode="json"),
                   "center_point": None,
                   "geometry_origin": request.geometry_origin,
                   "geometry_quality": request.geometry_quality.value,
                   "validation_state": (Validation.NEEDS_REVIEW.value if request.geometry_quality == Quality.APPROXIMATE
                                        else Validation.ACCEPTED.value),
                   "status": request.status or current.status,
                   "evidence": evidence}
        candidate = ProjectInput.model_validate(updated)
        result = repository.save_in_transaction(conn,candidate,expected_version_id=current.version_id)
        if result.version_id == current.version_id:
            raise ValueError("Verification made no change")
        audit = conn.execute("""INSERT INTO synchro.location_verifications
            (verification_id,project_id,from_version_id,to_version_id,actor_id,actor_role,reason,evidence)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
            RETURNING verification_id,project_id,from_version_id,to_version_id,
                      actor_id,actor_role,reason,evidence,occurred_at""",
            (uuid4(),project_id,current.version_id,result.version_id,request.actor_id,request.actor_role,
             request.reason,Jsonb({"geometry":request.geometry_evidence.model_dump(mode="json"),
                                   "status":request.status_evidence.model_dump(mode="json") if request.status_evidence else None}))).fetchone()
    return {"project": result.model_dump(mode="json"),
            "verification": {**audit,"verification_id":str(audit["verification_id"]),
                             "occurred_at":audit["occurred_at"].isoformat()}}


def verification_history(project_id):
    with repository.connect() as conn:
        if repository.current_project(conn,project_id) is None:
            return None
        rows = conn.execute("""SELECT verification_id,project_id,from_version_id,to_version_id,
                           actor_id,actor_role,reason,evidence,occurred_at
                           FROM synchro.location_verifications WHERE project_id=%s
                           ORDER BY occurred_at DESC,verification_id DESC""",(project_id,)).fetchall()
    return [{**r,"verification_id":str(r["verification_id"]),
             "occurred_at":r["occurred_at"].isoformat()} for r in rows]
