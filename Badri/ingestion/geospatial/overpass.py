"""Bounded bulk infrastructure queries, preserving the original response."""
from ingestion.catalog.aliases import ALIASES
from ingestion.common import IngestionError
from ingestion.geospatial.normalize_crs import normalize_geometry

ENDPOINT = "https://overpass-api.de/api/interpreter"
# south, west, north, east. Discovery regions, not utility territory boundaries.
REGIONS = {"savannah": [31.8, -81.7, 32.8, -80.4], "augusta": [32.8, -82.5, 34.0, -81.2]}


def build_query(utility, region):
    # Values come from fixed local dictionaries, not interpolated arbitrary QL.
    aliases = ALIASES[utility]
    pattern = "|".join(aliases).replace("&", ".")
    bbox = ",".join(str(v) for v in REGIONS[region])
    queries = [f'nwr["power"~"^(substation|line|minor_line|cable)$"]["{tag}"~"{pattern}",i]({bbox});'
               for tag in ("operator", "owner")]
    return "[out:json][timeout:30];\n(\n" + "\n".join(queries) + "\n);\nout body geom;"


def convert_response(response):
    if response.get("remark"):
        raise IngestionError("OVERPASS_INCOMPLETE", response["remark"], retryable=True)
    if not isinstance(response.get("elements"), list):
        raise IngestionError("OVERPASS_INVALID_RESPONSE", "Missing elements array")
    features, skipped = [], []
    for element in response["elements"]:
        feature_id = f"{element['type']}/{element['id']}"
        tags = element.get("tags", {})
        geometry = None
        if element["type"] == "node" and "lon" in element and "lat" in element:
            geometry = {"type": "Point", "coordinates": [element["lon"], element["lat"]]}
        elif element["type"] == "way" and len(element.get("geometry", [])) >= 2:
            points = element["geometry"]
            if all("lon" in p and "lat" in p for p in points):
                coords = [[p["lon"], p["lat"]] for p in points]
                polygon = tags.get("power") == "substation" and len(coords) >= 4 and coords[0] == coords[-1]
                geometry = {"type": "Polygon" if polygon else "LineString", "coordinates": [coords] if polygon else coords}
        if geometry is None:
            skipped.append({"provider_feature_id": feature_id, "reason": "UNSUPPORTED_OR_INCOMPLETE_GEOMETRY"})
            continue
        try:
            geometry = normalize_geometry(geometry, "EPSG:4326")
        except (ValueError, TypeError) as exc:
            skipped.append({"provider_feature_id": feature_id, "reason": str(exc)})
            continue
        features.append({"type": "Feature", "id": feature_id, "geometry": geometry,
                         "properties": {**tags, "provider_feature_id": feature_id}})
    return {"format": "overpass", "source_crs": "EPSG:4326", "canonical_crs": "EPSG:4326",
            "provider": "OPENSTREETMAP", "attribution": "© OpenStreetMap contributors (ODbL)",
            "provider_timestamp": response.get("osm3s", {}).get("timestamp_osm_base"),
            "geojson": {"type": "FeatureCollection", "features": features}, "skipped_features": skipped}
