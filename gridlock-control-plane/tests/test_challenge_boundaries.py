"""Cases absent from the organizer workbook but essential to honest ranking."""
from app.challenge.config import get_config
from app.challenge.contracts import ProjectInput, ProjectVersion
from app.challenge.engine import opportunity


def version(identifier, utility, *, geometry=None, quality="HIGH", validation="ACCEPTED", status="planned"):
    candidate = ProjectInput(
        project_id=identifier, utility_id=utility, project_name=identifier,
        project_type="transmission_line", status=status, location_text="recorded location",
        geometry=geometry, geometry_origin="SINGLE_LOCATED_POINT",
        geometry_quality=quality, validation_state=validation,
        evidence=[{"source_id":"source", "source_name":"Source"}],
    )
    return ProjectVersion(**candidate.model_dump(), version_id=f"PV-{identifier}", version_number=1)


def test_missing_unresolved_and_same_utility_do_not_create_opportunities():
    point = {"type":"Point", "coordinates":[-81,32]}
    known = version("a","A",geometry=point)
    measured = {"meters":0,"intersects":True,"closest_point_a":point,"closest_point_b":point}
    assert opportunity(known,version("b","B"),measured,get_config()) is None
    assert opportunity(known,version("b","B",geometry=point,validation="UNRESOLVED"),measured,get_config()) is None
    assert opportunity(known,version("b","A",geometry=point),measured,get_config()) is None
    assert opportunity(known,version("b","B",geometry=point,status="cancelled"),measured,get_config()) is None


def test_approximate_geometry_and_unknown_timing_are_disclosed():
    point = {"type":"Point", "coordinates":[-81,32]}
    first = version("a","A",geometry=point,quality="APPROXIMATE",validation="NEEDS_REVIEW")
    second = version("b","B",geometry=point)
    measured = {"meters":1000,"intersects":False,"closest_point_a":point,"closest_point_b":point}
    result = opportunity(first,second,measured,get_config())
    assert result["tier"] == "ROW_ACCESS"
    assert result["distance_status"] == "APPROXIMATE"
    assert result["temporal_relationship"] == {"type":"UNKNOWN","status":"UNAVAILABLE"}


def test_threshold_boundary_is_exclusive():
    point = {"type":"Point", "coordinates":[-81,32]}
    a,b = version("a","A",geometry=point),version("b","B",geometry=point)
    config = get_config()
    measured = {"meters":config.maximum_meters,"intersects":False,"closest_point_a":point,"closest_point_b":point}
    assert opportunity(a,b,measured,config) is None
