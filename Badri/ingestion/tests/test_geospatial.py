import json
from io import BytesIO
from zipfile import ZipFile

import pytest
import shapefile
from pyproj import Transformer

from ingestion.common import IngestionError
from ingestion.geospatial.candidate_builder import build_candidates
from ingestion.geospatial.normalize_crs import lon_lat, normalize_geometry
from ingestion.geospatial.overpass import build_query, convert_response
from ingestion.parsers.gis import parse_geojson, parse_shapefile
from ingestion.parsers.starter import coordinate_geometry


def test_projected_crs_preserves_longitude_latitude_order():
    x, y = Transformer.from_crs(4326, 26917, always_xy=True).transform(-81.1, 32.3)
    result = normalize_geometry({"type": "Point", "coordinates": [x, y]}, "EPSG:26917")
    assert result["coordinates"] == pytest.approx([-81.1, 32.3], abs=1e-7)


@pytest.mark.parametrize("point", [[181, 32], [-81, 91], [float("nan"), 32], [True, 32]])
def test_invalid_coordinates_rejected(point):
    with pytest.raises(IngestionError):
        lon_lat(*point)


def test_explicit_lat_lon_text_mapping():
    result = coordinate_geometry({"coords": "(32.2, -81.2); (32.4, -81.0)"},
                                 {"column": "coords", "order": "lat_lon"})
    assert result["coordinates"] == [[-81.2, 32.2], [-81.0, 32.4]]
    with pytest.raises(IngestionError, match="explicit"):
        coordinate_geometry({"coords": "32.2, -81.2"}, {"column": "coords"})


def test_geojson_preserves_source_crs_and_properties():
    document = {"type": "Feature", "id": "1", "properties": {"name": "Raw name"},
                "geometry": {"type": "Point", "coordinates": [-81.1, 32.3]}}
    parsed = parse_geojson(json.dumps(document))
    assert parsed["source_crs"] == parsed["canonical_crs"] == "EPSG:4326"
    assert parsed["geojson"]["features"][0]["properties"] == document["properties"]


def shapefile_zip():
    shp, shx, dbf = BytesIO(), BytesIO(), BytesIO()
    with shapefile.Writer(shp=shp, shx=shx, dbf=dbf, shapeType=shapefile.POINT) as writer:
        writer.field("name", "C")
        writer.point(-81.1, 32.3)
        writer.record("Synthetic station")
    output = BytesIO()
    with ZipFile(output, "w") as archive:
        for suffix, stream in [("shp", shp), ("shx", shx), ("dbf", dbf)]:
            archive.writestr(f"nested/test.{suffix}", stream.getvalue())
    return output.getvalue()


def test_shapefile_requires_crs_and_preserves_geometry():
    data = shapefile_zip()
    with pytest.raises(IngestionError, match="source-crs"):
        parse_shapefile(data)
    parsed = parse_shapefile(data, "EPSG:4326")
    assert parsed["geojson"]["features"][0]["geometry"]["coordinates"] == (-81.1, 32.3)
    assert parsed["source_crs"] == "EPSG:4326"


def test_overpass_is_bulk_bounded_and_no_invented_relation_geometry():
    query = build_query("DESC", "savannah")
    assert "31.8,-81.7,32.8,-80.4" in query
    assert "out body geom" in query
    parsed = convert_response({"elements": [
        {"type": "node", "id": 1, "lon": -81.1, "lat": 32.3, "tags": {"name": "Synthetic Alpha Substation", "power": "substation"}},
        {"type": "relation", "id": 2, "members": []}]})
    assert len(parsed["geojson"]["features"]) == 1
    assert parsed["skipped_features"][0]["provider_feature_id"] == "relation/2"
    assert parsed["geojson"]["features"][0]["geometry"]["coordinates"] == (-81.1, 32.3)
    with pytest.raises(IngestionError, match="timed out"):
        convert_response({"elements": [], "remark": "runtime error: timed out"})


def test_same_name_is_candidate_never_verification_and_keeps_alternatives():
    parsed = convert_response({"elements": [
        {"type": "node", "id": i, "lon": -81.1, "lat": 32.3,
         "tags": {"name": "Synthetic Alpha Substation", "power": "substation", "operator": operator}}
        for i, operator in [(1, "DESC"), (2, "Georgia Power")]]})
    projects = [{"project_candidate_id": "CP-1", "project_name": "Synthetic Alpha - Synthetic Beta 230 kV #2", "utility": "DESC"}]
    source = {"source_version_id": "SV-1", "publisher": "OSM", "retrieved_at": "2026-09-26T00:00:00Z", "source_type": "OPENSTREETMAP"}
    candidates = build_candidates(projects, parsed, source)
    assert len(candidates) == 2
    assert all(c["association_status"] == "UNVERIFIED" for c in candidates)
    assert [c["query_metadata"]["operator_match"] for c in candidates] == [True, False]
    assert all("verified" not in c for c in candidates)
