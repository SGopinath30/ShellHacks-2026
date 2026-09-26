from typing import Literal
from fastapi import APIRouter, HTTPException, Query, Security
from fastapi.security import APIKeyHeader
import psycopg
from . import repository
from .config import Profile, get_config
from .contracts import ProjectInput, ProjectVersion, Quality, geometry_status

router = APIRouter(prefix="/api/v1", tags=["SYNCHRO challenge v1"])
write_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def db_call(function,*args):
    try:
        return function(*args)
    except psycopg.Error as exc:
        raise HTTPException(503,"PostGIS unavailable or schema missing; run python -m scripts.init_challenge_db") from exc


@router.post("/project-versions",response_model=ProjectVersion,status_code=201)
def import_project(project: ProjectInput, _key: str | None = Security(write_key_header)):
    try:
        return db_call(repository.save,project)
    except ValueError as exc:
        raise HTTPException(409,str(exc)) from exc


def filtered(utility,status,voltage,quality):
    return [p for p in db_call(repository.projects)
            if (utility is None or p.utility_id == utility)
            and (status is None or p.status == status)
            and (voltage is None or p.voltage_kv == voltage)
            and (quality is None or p.geometry_quality == quality)]


@router.get("/projects",response_model=list[ProjectVersion])
def list_projects(utility: str | None = None,status: str | None = None,
                  voltage: float | None = Query(None,gt=0),geometry_quality: Quality | None = None):
    return filtered(utility,status,voltage,geometry_quality)


@router.get("/projects/geojson")
def geojson(utility: str | None = None,status: str | None = None,
            voltage: float | None = Query(None,gt=0),geometry_quality: Quality | None = None):
    features = []
    for p in filtered(utility,status,voltage,geometry_quality):
        properties = p.model_dump(mode="json",exclude={"geometry"})
        properties["geometry_status"] = geometry_status(p)
        features.append({"type":"Feature","id":p.project_id,
                         "geometry":p.geometry.model_dump(mode="json") if p.geometry else None,
                         "properties":properties})
    return {"type":"FeatureCollection","features":features}


def selected(profile,maximum,utility_a=None,utility_b=None,timeline_filter=None,geometry_quality=None):
    config = get_config(profile,maximum)
    rows = db_call(repository.opportunities,config)
    if utility_a and utility_b and utility_a == utility_b:
        return []
    return [r for r in rows
            if (utility_a is None or utility_a in [p["utility_id"] for p in r["projects"]])
            and (utility_b is None or utility_b in [p["utility_id"] for p in r["projects"]])
            and (timeline_filter is None or r["temporal_relationship"]["status"] == timeline_filter)
            and (geometry_quality is None or all(p["geometry_quality"] == geometry_quality for p in r["projects"]))]


@router.get("/opportunities")
def list_opportunities(profile: Profile = Profile.CHALLENGE_GEOMETRY,
                       utility_a: str | None = None,utility_b: str | None = None,
                       max_distance: float | None = Query(None,gt=0,allow_inf_nan=False,description="Strict maximum in meters"),
                       timeline_filter: Literal["CONFIRMED","POSSIBLE","NONE","KNOWN","UNAVAILABLE"] | None = None,
                       geometry_quality: Quality | None = None,
                       limit: int = Query(100,ge=1,le=1000),offset: int = Query(0,ge=0)):
    return selected(profile,max_distance,utility_a,utility_b,timeline_filter,geometry_quality)[offset:offset+limit]


@router.get("/opportunities/{pair_id}")
def detail(pair_id: str,profile: Profile = Profile.CHALLENGE_GEOMETRY,
           max_distance: float | None = Query(None,gt=0,allow_inf_nan=False)):
    for result in selected(profile,max_distance):
        if result["pair_id"] == pair_id:
            return result
    raise HTTPException(404,"Opportunity not found under this profile and configuration")
