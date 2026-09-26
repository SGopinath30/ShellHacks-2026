"""Explicit workbook mapping. Preserve every source cell; never infer a route."""
import re

from ingestion.catalog.aliases import utility_id
from ingestion.common import IngestionError, stable_id
from ingestion.geospatial.normalize_crs import lon_lat


def table(parsed, spec):
    sheets = [sheet for sheet in parsed["sheets"] if sheet["name"] == spec["sheet"]]
    if not sheets:
        raise IngestionError("MAPPING_ERROR", f"Missing sheet: {spec['sheet']}")
    rows = sheets[0]["rows"]
    header_number = spec.get("header_row", 1)
    header = next((row["values"] for row in rows if row["row_number"] == header_number), None)
    if header is None:
        raise IngestionError("MAPPING_ERROR", "Missing header row")
    named_headers = [v for v in header if v is not None]
    if len(named_headers) != len(set(named_headers)):
        raise IngestionError("MAPPING_ERROR", "Duplicate headers need an explicit source mapping")
    for row in rows:
        if row["row_number"] <= header_number:
            continue
        fields = {key: row["values"][index] if index < len(row["values"]) else None
                  for index, key in enumerate(header) if key is not None}
        yield header, fields, row


def coordinate_geometry(fields, spec):
    if "points" in spec:
        pairs = [[fields[p["longitude"]], fields[p["latitude"]]] for p in spec["points"]]
    else:
        value = fields[spec["column"]]
        if value in (None, ""):
            return None
        if spec.get("order") not in ("lon_lat", "lat_lon"):
            raise IngestionError("MAPPING_ERROR", "Text coordinates require explicit lon_lat or lat_lon order")
        pairs = []
        for part in str(value).split(spec.get("separator", ";")):
            # Decimal pairs only; DMS, named endpoints and formulas require review.
            match = re.fullmatch(r"\s*\(?\s*([+-]?\d+(?:\.\d+)?)\s*,\s*([+-]?\d+(?:\.\d+)?)\s*\)?\s*", part)
            if not match:
                raise IngestionError("INVALID_COORDINATE", "Expected decimal coordinate pairs")
            pair = list(match.groups())
            pairs.append(pair if spec["order"] == "lon_lat" else pair[::-1])
    present = [pair for pair in pairs if any(v not in (None, "") for v in pair)]
    if not present:
        return None
    if any(any(v in (None, "") for v in pair) for pair in present):
        raise IngestionError("INCOMPLETE_COORDINATE", "Both longitude and latitude are required")
    points = [lon_lat(*pair) for pair in present]
    if len(points) not in (1, 2):
        raise IngestionError("INVALID_COORDINATE", "Starter geometry supports one or two points")
    if len(points) == 2 and points[0] == points[1]:
        raise IngestionError("DEGENERATE_SEGMENT", "Endpoint coordinates are identical")
    return {"type": "Point" if len(points) == 1 else "LineString",
            "coordinates": points[0] if len(points) == 1 else points}


def map_starter(parsed, mapping, source):
    projects, overlaps, candidates = [], [], []
    seen = set()
    for spec in mapping["projects"]:
        for header, fields, row in table(parsed, spec):
            try:
                values = {key: fields[column] for key, column in spec["columns"].items()}
                if any(values.get(key) in (None, "") for key in ("starter_id", "project_name")):
                    raise IngestionError("MAPPING_ERROR", f"Missing project ID/name in row {row['row_number']}")
                project_id = str(values["starter_id"])
                if project_id in seen:
                    raise IngestionError("MAPPING_ERROR", f"Duplicate starter ID: {project_id}")
                seen.add(project_id)
                raw_utility = values.get("utility", spec.get("utility"))
                project = {
                    **values, "starter_id": project_id, "project_candidate_id": stable_id("CP", [source["source_version_id"], project_id]),
                    "utility_raw": raw_utility, "utility": utility_id(raw_utility) or raw_utility,
                    "record_origin": "STARTER_PACKAGE", "data_label": "STARTER_DATA",
                    "currentness": "UNVERIFIED_CURRENTNESS", "association_status": "UNVERIFIED",
                    "synthetic": source["source_type"] == "SYNTHETIC",
                    "source_version_id": source["source_version_id"],
                    "source_locator": {"sheet": spec["sheet"], "row_number": row["row_number"]},
                    "raw_headers": header, "raw_values": row["values"], "raw_fields": fields,
                    "raw_in_service_date": values.get("raw_in_service_date"),
                    "geometry_issue": None,
                }
                geometry = None
                coordinate_spec = spec.get("coordinates")
                if coordinate_spec:
                    coordinate_columns = ([coordinate_spec["column"]] if "column" in coordinate_spec else
                                          [column for point in coordinate_spec["points"] for column in point.values()])
                    project["raw_coordinates"] = {col: fields[col] for col in coordinate_columns}
                    try:
                        geometry = coordinate_geometry(fields, coordinate_spec)
                    except (ValueError, TypeError) as exc:
                        project["geometry_issue"] = {"error_code": getattr(exc, "code", "INVALID_COORDINATE"), "message": str(exc)}
                else:
                    project["raw_coordinates"] = None
                if geometry:
                    candidates.append({
                        "geometry_candidate_id": stable_id("GC", [project["project_candidate_id"], geometry]),
                        "project_candidate_id": project["project_candidate_id"],
                        "source_version_id": source["source_version_id"], "provider": "STARTER_PACKAGE",
                        "provider_feature_id": f"{spec['sheet']}!{row['row_number']}",
                        "feature_name": values["project_name"], "operator_raw": raw_utility,
                        "feature_type": "UNKNOWN", "geometry": geometry,
                        "source_crs": "EPSG:4326", "canonical_crs": "EPSG:4326",
                        "geometry_origin": "TWO_ENDPOINT_SEGMENT" if geometry["type"] == "LineString" else "STARTER_POINT",
                        "geometry_quality": "APPROXIMATE", "association_status": "UNVERIFIED",
                        "discovery_method": "WORKBOOK_MAPPING", "query_metadata": {"mapping": coordinate_spec},
                        "source_locator": project["source_locator"], "retrieved_at": source["retrieved_at"],
                        "synthetic": project["synthetic"],
                    })
                projects.append(project)
            except KeyError as exc:
                raise IngestionError("MAPPING_ERROR", f"Missing mapped column/key: {exc}") from exc
    for spec in mapping.get("overlaps", []):
        for header, fields, row in table(parsed, spec):
            try:
                mapped = {key: fields[column] for key, column in spec.get("columns", {}).items()}
            except KeyError as exc:
                raise IngestionError("MAPPING_ERROR", f"Missing overlap column: {exc}") from exc
            for key in ("project_id_a", "project_id_b"):
                if key in mapped and mapped[key] not in seen:
                    raise IngestionError("UNKNOWN_OVERLAP_PROJECT", str(mapped[key]))
            overlaps.append({**mapped, "record_origin": "STARTER_PACKAGE", "data_label": "STARTER_DATA",
                             "currentness": "UNVERIFIED_CURRENTNESS", "association_status": "UNVERIFIED",
                             "source_version_id": source["source_version_id"],
                             "source_locator": {"sheet": spec["sheet"], "row_number": row["row_number"]},
                             "raw_headers": header, "raw_values": row["values"], "raw_fields": fields})
    if "expected_project_count" in mapping and len(projects) != mapping["expected_project_count"]:
        raise IngestionError("PROJECT_COUNT_MISMATCH", f"Expected {mapping['expected_project_count']}, parsed {len(projects)}")
    if "expected_overlap_count" in mapping and len(overlaps) != mapping["expected_overlap_count"]:
        raise IngestionError("OVERLAP_COUNT_MISMATCH", f"Expected {mapping['expected_overlap_count']}, parsed {len(overlaps)}")
    return projects, overlaps, candidates
