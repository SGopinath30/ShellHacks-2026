import math

from pyproj import CRS, Transformer
from shapely.geometry import mapping, shape
from shapely.ops import transform

from ingestion.common import IngestionError


def lon_lat(longitude, latitude):
    if isinstance(longitude, bool) or isinstance(latitude, bool):
        raise IngestionError("INVALID_COORDINATE", "Boolean coordinate")
    lon, lat = float(longitude), float(latitude)
    if not (math.isfinite(lon) and math.isfinite(lat) and -180 <= lon <= 180 and -90 <= lat <= 90):
        raise IngestionError("INVALID_COORDINATE", f"Out of range longitude/latitude: {lon}, {lat}")
    return [lon, lat]


def normalize_geometry(geometry, source_crs):
    if not source_crs:
        raise IngestionError("MISSING_CRS", "GIS inputs require a known source CRS")
    source = CRS.from_user_input(source_crs)
    geom = shape(geometry)
    if geom.is_empty or not geom.is_valid:
        raise IngestionError("INVALID_GEOMETRY", "Empty or invalid geometry; no automatic repair")
    if source != CRS.from_epsg(4326):
        transformer = Transformer.from_crs(source, "EPSG:4326", always_xy=True)
        geom = transform(lambda x, y, z=None: transformer.transform(x, y, z, errcheck=True), geom)
    result = mapping(geom)

    def check(coords):
        if not coords:
            raise IngestionError("INVALID_GEOMETRY", "Empty coordinates")
        if isinstance(coords[0], (int, float)):
            lon_lat(*coords[:2])
        else:
            for child in coords:
                check(child)

    def check_geometry(value):
        if value["type"] == "GeometryCollection":
            for child in value["geometries"]:
                check_geometry(child)
        else:
            check(value["coordinates"])

    check_geometry(result)
    return result
