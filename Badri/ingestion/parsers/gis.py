import json
from io import BytesIO
from pathlib import PurePosixPath
from zipfile import ZipFile

import shapefile
from pyproj import CRS

from ingestion.common import IngestionError
from ingestion.geospatial.normalize_crs import normalize_geometry


def parse_geojson(data, source_crs=None):
    document = json.loads(data)
    declared = document.get("crs", {}).get("properties", {}).get("name")
    if declared and source_crs and CRS.from_user_input(declared) != CRS.from_user_input(source_crs):
        raise IngestionError("CRS_CONFLICT", "Declared and supplied CRS disagree")
    original_crs = declared or source_crs or "EPSG:4326"
    if document["type"] == "FeatureCollection":
        features = document["features"]
    elif document["type"] == "Feature":
        features = [document]
    else:
        features = [{"type": "Feature", "geometry": document, "properties": {}}]
    result = []
    for feature in features:
        result.append({**feature, "geometry": normalize_geometry(feature["geometry"], original_crs)})
    return {"format": "geojson", "source_crs": original_crs, "canonical_crs": "EPSG:4326",
            "geojson": {"type": "FeatureCollection", "features": result}}


def parse_shapefile(data, source_crs=None):
    with ZipFile(BytesIO(data)) as archive:
        if sum(item.file_size for item in archive.infolist()) > 250 * 1024 * 1024:
            raise IngestionError("ARCHIVE_TOO_LARGE", "Uncompressed shapefile exceeds 250 MiB")
        names = archive.namelist()
        shapes = [name for name in names if name.lower().endswith(".shp")]
        if len(shapes) != 1:
            raise IngestionError("SHAPEFILE_SELECTION_REQUIRED", "ZIP must contain exactly one shapefile")
        stem = str(PurePosixPath(shapes[0]).with_suffix(""))
        members = {name.lower(): name for name in names}

        def member(suffix, required=True):
            name = members.get((stem + suffix).lower())
            if not name:
                if required:
                    raise IngestionError("MISSING_SHAPEFILE_COMPONENT", suffix)
                return None
            return archive.read(name)

        prj = member(".prj", False)
        declared = prj.decode("utf-8-sig").strip() if prj else None
        if declared and source_crs and CRS.from_user_input(declared) != CRS.from_user_input(source_crs):
            raise IngestionError("CRS_CONFLICT", "PRJ and supplied CRS disagree")
        original_crs = declared or source_crs
        if not original_crs:
            raise IngestionError("MISSING_CRS", "Supply --source-crs or include .prj")
        cpg = member(".cpg", False)
        encoding = cpg.decode("ascii").strip() if cpg else "utf-8"
        if encoding == "65001":
            encoding = "utf-8"
        # Read archive members in memory; never extract untrusted ZIP paths.
        with shapefile.Reader(shp=BytesIO(member(".shp")), shx=BytesIO(member(".shx")),
                              dbf=BytesIO(member(".dbf")), encoding=encoding) as reader:
            features = [{"type": "Feature", "id": index,
                         "properties": record.record.as_dict(),
                         "geometry": normalize_geometry(record.shape.__geo_interface__, original_crs)}
                        for index, record in enumerate(reader.iterShapeRecords())]
    return {"format": "shapefile", "source_crs": original_crs, "canonical_crs": "EPSG:4326",
            "geojson": {"type": "FeatureCollection", "features": features}}
