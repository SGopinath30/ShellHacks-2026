from pathlib import Path

from ingestion.common import IngestionError, stable_id, write_json
from ingestion.geospatial.candidate_builder import build_candidates
from ingestion.parsers.starter import map_starter
from ingestion.versioning.sources import check_access


def export_starter(store, source, parsed, mapping, geospatial=(), supporting=()):
    geospatial, supporting = list(geospatial), list(supporting)
    sources = [source] + [item[0] for item in geospatial + supporting]
    for record in sources:
        check_access(record["access_class"], handoff=True)
        store.raw_bytes(record)
    projects, overlaps, candidates = map_starter(parsed, mapping, source)
    for record, geo in geospatial:
        candidates.extend(build_candidates(projects, geo, record))
    package_id = stable_id("PKG", [mapping, sources, parsed, geospatial, supporting])
    output = store.root / "fixtures" / package_id
    if not projects:
        raise IngestionError("NO_PROJECTS", "Mapping produced no projects")
    report = {
        "project_count": len(projects), "overlap_fixture_count": len(overlaps),
        "projects_with_names": sum(bool(p["project_name"]) for p in projects),
        "projects_with_utility_ids": sum(p["utility"] in ("DESC", "GPC") for p in projects),
        "projects_with_schedule_values": sum(p["raw_in_service_date"] not in (None, "") for p in projects),
        "projects_with_geometry": len({c["project_candidate_id"] for c in candidates}),
        "starter_two_endpoint_segments": sum(c["geometry_origin"] == "TWO_ENDPOINT_SEGMENT" for c in candidates),
        "starter_points": sum(c["geometry_origin"] == "STARTER_POINT" for c in candidates),
        "starter_point_project_ids": [p["starter_id"] for p in projects if any(
            c["project_candidate_id"] == p["project_candidate_id"] and c["geometry_origin"] == "STARTER_POINT"
            for c in candidates)],
        "geometry_issues": [{"starter_id": p["starter_id"], **p["geometry_issue"]} for p in projects if p["geometry_issue"]],
        "projects_with_current_first_party_source": 0,
        "supporting_source_count": len(supporting),
        "osm_candidate_count": sum(c["provider"] == "OPENSTREETMAP" for c in candidates),
        "projects_needing_current_source": [p["starter_id"] for p in projects],
        "synthetic": any(p["synthetic"] for p in projects),
        "notes": ["Current source association requires Mac review.",
                  "Starter overlap rows are fixture claims, not calculated findings.",
                  "All geometry associations are unverified."],
    }
    inventory = [{"starter_id": p["starter_id"], "project": p["project_name"], "utility": p["utility"],
                  "known_source_version_ids": [p["source_version_id"]],
                  "source_url": source.get("source_url"), "source_file": source.get("original_filename"),
                  "geometry_candidate_count": sum(c["project_candidate_id"] == p["project_candidate_id"] for c in candidates),
                  "schedule_available": p["raw_in_service_date"] not in (None, ""),
                  "current_first_party_source": None, "current_source_status": "NEEDS_DISCOVERY"} for p in projects]
    for entry in inventory:
        entry["utility_document_candidates"] = [
            {"source_version_id": record["source_version_id"], "source_file": record.get("original_filename"),
             "title": record["title"], "association_status": "UNVERIFIED",
             "currentness": "UNVERIFIED_CURRENTNESS", "discovery_basis": "SUPPLIED_DOCUMENT_FOR_SAME_UTILITY"}
            for record, _ in supporting if record.get("utility") == entry["utility"] and record["source_tier"] == "A"]
    package = {"schema_version": "0.1.0", "package_id": package_id,
               "association_status": "UNVERIFIED", "data_label": "STARTER_DATA",
               "currentness": "UNVERIFIED_CURRENTNESS", "synthetic": report["synthetic"],
               "review_required": any(s["access_class"] == "PUBLIC_ASSUMED" for s in sources),
               "source_records": sources, "project_seeds": projects, "geometry_candidates": candidates}
    for filename, value in [("starter_projects.json", projects), ("starter_overlaps.json", overlaps),
                            ("geometry_candidates.json", candidates), ("source_inventory.json", inventory),
                            ("quality_report.json", report), ("mac_handoff.json", package), ("mapping.json", mapping)]:
        write_json(output / filename, value)
    # Portable package: exact bytes and parser output travel with the manifest.
    for record, representation in [(source, parsed), *geospatial, *supporting]:
        raw_output = output / record["raw_path"]
        raw_output.parent.mkdir(parents=True, exist_ok=True)
        content = store.raw_bytes(record)
        if not raw_output.exists():
            raw_output.write_bytes(content)
        elif raw_output.read_bytes() != content:
            raise IngestionError("RAW_INTEGRITY_ERROR", str(raw_output))
        write_json(output / "evidence" / f"{record['source_version_id']}.json", representation)
    return Path(output), report
