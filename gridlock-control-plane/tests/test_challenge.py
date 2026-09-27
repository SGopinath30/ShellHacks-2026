import json
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from app.main import app
from app.challenge.config import Profile,get_config
from app.challenge.contracts import Construction,ProjectInput
from app.challenge.engine import pair_id,tier
from app.challenge.repository import connect,health,opportunities
from app.challenge.temporal import relationship


FIXTURES = Path(__file__).resolve().parents[1]/"data/fixtures"


def project(name,utility,geometry,**changes):
    record = {"project_id":name,"utility_id":utility,"project_name":name,
              "project_type":"transmission_line","status":"planned","location_text":"source location",
              "geometry":geometry,"geometry_origin":"PUBLIC_GIS","geometry_quality":"HIGH",
              "validation_state":"ACCEPTED","evidence":[{"source_id":"source","source_name":"Test source"}]}
    record.update(changes)
    return ProjectInput.model_validate(record)


def test_invalid_geometry_and_partial_schedule():
    with pytest.raises(ValidationError):
        project("x","A",{"type":"Point","coordinates":[200,30]})
    with pytest.raises(ValidationError):
        project("x","A",{"type":"LineString","coordinates":[[-81,32]]})
    with pytest.raises(ValidationError):
        Construction(start={"earliest":"2026-04-01","latest":"2026-04-01"},
                     end_exclusive={"earliest":"2026-03-01","latest":"2026-03-01"})


def test_temporal_types_are_separate():
    a = Construction(start={"earliest":"2026-04-01","latest":"2026-05-01"},
                     end_exclusive={"earliest":"2027-01-01","latest":"2027-02-01"})
    b = Construction(start={"earliest":"2026-06-01","latest":"2026-06-01"},
                     end_exclusive={"earliest":"2027-03-01","latest":"2027-03-01"})
    result = relationship(a,b)
    assert result["status"] == "CONFIRMED"
    assert result["minimum_overlap_days"] <= result["maximum_overlap_days"]
    milestone = project("m","B",{"type":"Point","coordinates":[-81,32]},
                        schedule={"type":"IN_SERVICE_GAP","in_service_date":"2027-01-01"}).schedule
    assert relationship(a,milestone) == {"type":"UNKNOWN","status":"UNAVAILABLE"}


def test_stable_identity_and_strict_threshold():
    assert pair_id("A","B") == pair_id("B","A")
    config = get_config()
    assert tier(config.maximum_meters,False,config) == "OUT_OF_RANGE"
    assert tier(0,True,config) == "CROSSING_TOUCHING"


@pytest.mark.skipif(health()["status"] != "ok",reason="PostGIS not running; run init_challenge_db")
def test_postgis_geometry_and_closest_points():
    with connect() as conn:
        rows = conn.execute("""
            SELECT ST_Distance(a.g::geography,b.g::geography) AS meters,
              ST_Intersects(a.g,b.g) AS touches,
              ST_AsGeoJSON(ST_ClosestPoint(a.g::geography,b.g::geography)::geometry)::json AS closest
            FROM (SELECT ST_GeomFromText('LINESTRING(-81 32,-80 32)',4326) AS g) a,
                 (SELECT ST_GeomFromText('LINESTRING(-80.5 31.5,-80.5 32.5)',4326) AS g) b
            """).fetchone()
        assert rows["touches"] and rows["meters"] == 0
        near = conn.execute("""
            SELECT ST_Distance(ST_GeomFromText('POINT(-80.5 32.01)',4326)::geography,
                               ST_GeomFromText('LINESTRING(-81 32,-80 32)',4326)::geography) AS meters
            """).fetchone()["meters"]
        assert 1000 < near < 1200
        parallel = conn.execute("""
            SELECT ST_Distance(ST_GeomFromText('LINESTRING(-81 32,-80 32)',4326)::geography,
                               ST_GeomFromText('LINESTRING(-81 32.01,-80 32.01)',4326)::geography) AS meters
            """).fetchone()["meters"]
        assert 1000 < parallel < 1200


@pytest.mark.skipif(health()["status"] != "ok",reason="PostGIS not running; run init_challenge_db")
def test_starter_overlap_fixture_and_api():
    expected = json.loads((FIXTURES/"starter_overlaps.json").read_text())
    fixture_ids = {p["project_id"] for p in json.loads((FIXTURES/"starter_projects.json").read_text())}
    actual = [r for r in opportunities(get_config(Profile.STARTER_COMPATIBILITY))
              if r["project_a"] in fixture_ids and r["project_b"] in fixture_ids]
    pairs = {frozenset((r["project_a"],r["project_b"])):r for r in actual}
    assert len(actual) == len(expected) == 6
    for row in expected:
        result = pairs[frozenset((row["project_a"],row["project_b"]))]
        assert abs(result["distance"]["display_miles"]-row["organizer_distance_miles"]) < 0.02
        assert result["temporal_relationship"]["gap_days"] == row["organizer_gap_days"]
    client = TestClient(app)
    assert client.get("/health").status_code == 200
    assert len(client.get("/api/v1/projects").json()) >= 10
    assert client.get("/api/v1/projects/geojson").json()["type"] == "FeatureCollection"
    detail = client.get(f"/api/v1/opportunities/{actual[0]['pair_id']}",params={"profile":"STARTER_COMPATIBILITY"})
    assert detail.status_code == 200
    assert detail.json()["distance"]["method"] == "CENTER_POINT_HAVERSINE"
