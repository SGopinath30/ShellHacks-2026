"""Pure ranking and presentation of measured spatial pairs."""
import hashlib
import json
import math
from .config import Profile
from .contracts import Point, geometry_status
from .temporal import relationship, strength

TIERS = ("CROSSING_TOUCHING", "ROW_ACCESS", "SITE_LOGISTICS", "CREW_EQUIPMENT", "OUT_OF_RANGE")
AREAS = {
    "CROSSING_TOUCHING": ["crossing review", "right-of-way coordination"],
    "ROW_ACCESS": ["access", "right-of-way coordination"],
    "SITE_LOGISTICS": ["staging", "deliveries", "site logistics"],
    "CREW_EQUIPMENT": ["mobilization", "crew scheduling", "equipment scheduling"],
}


def pair_id(first, second):
    raw = json.dumps(sorted((first, second)), ensure_ascii=False, separators=(",", ":"))
    return "P-" + hashlib.sha256(raw.encode()).hexdigest()


def center(project):
    # For lines, use only a source-provided center. Never invent a midpoint.
    return project.center_point or (project.geometry if isinstance(project.geometry, Point) else None)


def haversine(first, second, config):
    lon1, lat1 = map(math.radians, first)
    lon2, lat2 = map(math.radians, second)
    h = math.sin((lat2-lat1)/2)**2 + math.cos(lat1)*math.cos(lat2)*math.sin((lon2-lon1)/2)**2
    return 2 * config.earth_radius_meters * math.asin(math.sqrt(max(0, min(1, h))))


def tier(distance, intersects, config):
    if distance >= config.maximum_meters:
        return "OUT_OF_RANGE"
    if intersects:
        return "CROSSING_TOUCHING"
    if distance < config.row_access_meters:
        return "ROW_ACCESS"
    if distance < config.site_logistics_meters:
        return "SITE_LOGISTICS"
    return "CREW_EQUIPMENT"


def opportunity(a, b, measured, config):
    if a.utility_id == b.utility_id or any(p.status not in config.eligible_statuses and not p.is_fixture for p in (a,b)):
        return None
    if any(geometry_status(p) == "UNAVAILABLE" for p in (a,b)):
        return None
    category = tier(measured["meters"], measured["intersects"], config)
    if category == "OUT_OF_RANGE":
        return None
    temporal = relationship(a.schedule, b.schedule)
    quality = "APPROXIMATE" if config.profile == Profile.STARTER_COMPATIBILITY or any(geometry_status(p) == "APPROXIMATE" for p in (a,b)) else "CALCULABLE"
    identity = pair_id(a.project_id,b.project_id)
    return {
        "pair_id": identity, "project_a": a.project_id, "project_b": b.project_id,
        "distance": {"meters": measured["meters"], "display_miles": measured["meters"] / config.meters_per_mile,
                     "method": "CENTER_POINT_HAVERSINE" if config.profile == Profile.STARTER_COMPATIBILITY else "MINIMUM_GEOMETRY_DISTANCE",
                     "geometry_a_version": a.version_id, "geometry_b_version": b.version_id,
                     "geometry_quality": quality, "geometry_origins": [a.geometry_origin,b.geometry_origin],
                     "engine_version": config.engine_version},
        "distance_status": quality, "intersects": measured["intersects"],
        "closest_point_a": measured["closest_point_a"], "closest_point_b": measured["closest_point_b"],
        "tier": category, "potential_coordination_category": category,
        "possible_coordination_areas": AREAS[category], "temporal_relationship": temporal,
        "temporal_strength": ("CONFIRMED_CONSTRUCTION_OVERLAP", "POSSIBLE_CONSTRUCTION_OVERLAP",
                              "CLOSE_IN_SERVICE_MILESTONES", "NO_KNOWN_OVERLAP", "UNKNOWN")[strength(temporal,config)],
        "rank_key": [TIERS.index(category), measured["meters"], strength(temporal,config), identity],
        "calculation_configuration": config.model_dump(mode="json"), "boundary_version": None,
        "is_fixture": a.is_fixture or b.is_fixture,
        "projects": [a.model_dump(mode="json"),b.model_dump(mode="json")],
    }
