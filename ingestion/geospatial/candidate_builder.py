import re

from ingestion.catalog.aliases import normalize_name, utility_id
from ingestion.common import stable_id


def endpoint_names(project_name):
    text = re.sub(r"\b\d+(?:\.\d+)?\s*k[vV]\b.*", "", str(project_name), flags=re.I)
    parts = re.split(r"\s*[-–—]\s*|\s+to\s+", text, flags=re.I)
    return [clean_name(part) for part in parts if clean_name(part)]


def clean_name(name):
    return normalize_name(re.sub(r"\b(substation|station|sub)\b", "", str(name), flags=re.I))


def build_candidates(projects, parsed, source):
    candidates = []
    for project in projects:
        explicit_names = [project.get("endpoint_name_a"), project.get("endpoint_name_b")]
        endpoints = [clean_name(name) for name in explicit_names if name] or endpoint_names(project["project_name"])
        for feature in parsed["geojson"]["features"]:
            properties = feature.get("properties") or {}
            name = properties.get("name", "")
            normalized = clean_name(name)
            matches = [endpoint for endpoint in endpoints if endpoint == normalized or
                       (endpoint and f" {endpoint} " in f" {normalized} ")]
            if not matches:
                continue
            operator = properties.get("operator") or properties.get("owner")
            operator_id = utility_id(operator)
            feature_id = str(feature.get("id", properties.get("provider_feature_id", "")))
            if not feature_id:
                feature_id = stable_id("FEATURE", feature)
            candidates.append({
                "geometry_candidate_id": stable_id("GC", [project["project_candidate_id"], source["source_version_id"], feature_id, feature["geometry"]]),
                "project_candidate_id": project["project_candidate_id"], "source_version_id": source["source_version_id"],
                "provider": parsed.get("provider", source["publisher"]), "provider_feature_id": feature_id,
                "feature_name": name, "operator_raw": operator, "utility_search_id": operator_id,
                "feature_type": str(properties.get("power", "UNKNOWN")).upper(),
                "geometry": feature["geometry"], "source_crs": parsed["source_crs"], "canonical_crs": "EPSG:4326",
                "geometry_origin": "MAPPED_EXISTING_INFRASTRUCTURE", "geometry_quality": "PROVIDER_GEOMETRY",
                "association_status": "UNVERIFIED", "discovery_method": "LOCAL_NAME_FILTER",
                "query_metadata": {**source.get("query_metadata", {}), "matched_names": matches,
                                   "operator_match": None if operator_id is None else operator_id == project["utility"],
                                   "voltage_raw": properties.get("voltage"),
                                   "provider_timestamp": parsed.get("provider_timestamp")},
                "retrieved_at": source["retrieved_at"], "provider_properties": properties,
                "synthetic": project.get("synthetic", False) or source["source_type"] == "SYNTHETIC",
            })
    return candidates
