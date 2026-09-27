"""Sponsor tier cutoffs and geography-first ranking."""
from app.challenge.config import get_config
from app.challenge.contracts import ProjectInput, ProjectVersion
from app.challenge.engine import opportunity, tier


def record(identifier, utility, milestone=None):
    candidate = ProjectInput(
        project_id=identifier, utility_id=utility, project_name=identifier,
        project_type="transmission_line", status="planned", location_text="source location",
        geometry={"type":"Point", "coordinates":[-81,32]},
        geometry_origin="MANUAL_VERIFIED", geometry_quality="HIGH", validation_state="ACCEPTED",
        evidence=[{"source_id":"s", "source_name":"Source"}],
        schedule={"type":"IN_SERVICE_GAP", "in_service_date":milestone} if milestone else {"type":"UNKNOWN"},
    )
    return ProjectVersion(**candidate.model_dump(), version_id=f"PV-{identifier}", version_number=1)


def measured(meters):
    point = {"type":"Point", "coordinates":[-81,32]}
    return {"meters":meters, "intersects":False, "closest_point_a":point, "closest_point_b":point}


def test_all_distance_tiers_and_exact_cutoffs():
    config = get_config()
    assert tier(0,True,config) == "CROSSING_TOUCHING"
    assert tier(0,False,config) == "ROW_ACCESS"
    assert tier(1599.999,False,config) == "ROW_ACCESS"
    assert tier(1600,False,config) == "SITE_LOGISTICS"
    assert tier(7999.999,False,config) == "SITE_LOGISTICS"
    assert tier(8000,False,config) == "CREW_EQUIPMENT"
    assert tier(39999.999,False,config) == "CREW_EQUIPMENT"
    assert tier(40000,False,config) == "OUT_OF_RANGE"
    assert tier(40000,True,config) == "OUT_OF_RANGE"


def test_closer_pair_ranks_before_stronger_timing_within_same_tier():
    config = get_config()
    a = record("a","A","2027-01-01")
    near_unknown = opportunity(a,record("b","B"),measured(2000),config)
    farther_close_dates = opportunity(a,record("c","C","2027-01-01"),measured(3000),config)
    assert near_unknown["tier"] == farther_close_dates["tier"] == "SITE_LOGISTICS"
    assert near_unknown["rank_key"] < farther_close_dates["rank_key"]
    assert near_unknown["temporal_strength"] == "UNKNOWN"
    assert farther_close_dates["temporal_strength"] == "CLOSE_IN_SERVICE_MILESTONES"
