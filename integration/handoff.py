"""Export Mac-accepted versions as ASUS project inputs, without uploading them.

Run from the repository root with the shared Python environment:
    python -m integration.handoff --accepted PATH --output-dir PATH
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "Tarun"))
sys.path.insert(0, str(ROOT / "gridlock-control-plane"))

from app.challenge.contracts import ProjectInput  # noqa: E402
from project_intelligence.contracts import AcceptedProjectVersion  # noqa: E402


STATUS = {
    "PROPOSED": "proposed", "PLANNED": "planned", "APPROVED": "approved",
    "IN_PROGRESS": "in_progress", "CANCELLED": "cancelled", "UNKNOWN": "unknown",
}
PROJECT_TYPE = {
    "TRANSMISSION_LINE": "transmission_line", "SUBSTATION": "substation",
    "RECONDUCTORING": "upgrade", "TRANSFORMER": "upgrade",
}
GEOMETRY_ORIGIN = {
    "OPENSTREETMAP": "OSM_MATCH", "UTILITY_GIS": "UTILITY_GIS",
    "OPEN_INFRASTRUCTURE_MAP": "PUBLIC_GIS", "RTO_ISO": "PUBLIC_GIS",
    "TWO_ENDPOINT_SEGMENT": "TWO_ENDPOINT_SEGMENT", "OTHER": "PUBLIC_GIS",
}


def source_index(path: Path | None) -> dict[str, dict]:
    if path is None:
        return {}
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    rows = data.get("source_records", data.get("sources", [])) if isinstance(data, dict) else data
    return {row["source_version_id"]: row for row in rows}


def locator_text(locator) -> str | None:
    parts = []
    for name in ("page", "sheet", "row", "column", "element_id", "provider_feature_id"):
        value = getattr(locator, name)
        if value is not None:
            parts.append(f"{name} {value}")
    return ", ".join(parts) or None


def convert(version: AcceptedProjectVersion, sources: dict[str, dict] | None = None) -> ProjectInput:
    """Preserve accepted facts while withholding geometry that Mac has not accepted."""
    sources = sources or {}
    candidate = version.candidate
    if candidate.version_state.value == "STARTER_DATA":
        is_fixture = True
    else:
        is_fixture = False
    geo = candidate.geometry_candidate
    check = candidate.geometry_validation
    geometry_accepted = bool(
        geo and check and check.status.value == "ACCEPTED"
        and check.quality.value == "HIGH"
        and geo.geojson.get("type") in {"Point", "LineString"}
        and geo.provider.value != "TWO_ENDPOINT_SEGMENT"
    )
    geometry = geo.geojson if geometry_accepted and geo else None
    origin = GEOMETRY_ORIGIN.get(geo.provider.value, "PUBLIC_GIS") if geometry_accepted and geo else "CENTER_POINT"
    location = ", ".join(
        value.value for value in (candidate.county, candidate.state) if value and value.value
    ) or "Project-specific location requires verification"
    schedule = {"type": "UNKNOWN"}
    if (candidate.schedule and candidate.schedule.type.value == "IN_SERVICE_MILESTONE"
            and candidate.schedule.date and candidate.schedule.state.value in {"VERIFIED_RULE", "VERIFIED_HUMAN"}):
        schedule = {"type": "IN_SERVICE_GAP", "in_service_date": candidate.schedule.date.isoformat()}
    evidence = []
    for item in candidate.field_evidence:
        source = sources.get(item.source_version_id, {})
        evidence.append({
            "source_id": item.source_version_id,
            "source_name": source.get("title") or source.get("source_name") or item.source_version_id,
            "source_url": source.get("source_url"),
            "page_or_row": locator_text(item.locator),
            "snippet": item.original_text,
        })
    payload = {
        "project_id": candidate.external_project_id or version.project_identity,
        "utility_id": candidate.utility_id,
        "project_name": candidate.name.value,
        "project_type": PROJECT_TYPE.get(candidate.project_type.value.value if candidate.project_type and candidate.project_type.value else "", "other"),
        "status": STATUS.get(candidate.status.value.value if candidate.status and candidate.status.value else "", "unknown"),
        "voltage_kv": candidate.voltage_kv.value if candidate.voltage_kv else None,
        "location_text": location,
        "geometry": geometry,
        "geometry_origin": origin,
        "geometry_quality": "HIGH" if geometry_accepted else "UNRESOLVED",
        "validation_state": "ACCEPTED" if geometry_accepted and not is_fixture else "NEEDS_REVIEW",
        "source_crs": "EPSG:4326",
        "schedule": schedule,
        "evidence": evidence,
        "source_version_ids": [candidate.source_version_id, *candidate.supporting_source_version_ids],
        "upstream_project_version_id": version.project_version_id,
        "upstream_candidate_id": candidate.candidate_project_id,
        "is_fixture": is_fixture,
    }
    return ProjectInput.model_validate(payload)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--accepted", type=Path, required=True, help="AcceptedProjectVersion JSON file or directory")
    parser.add_argument("--source-manifest", type=Path, help="Dell or Mac source manifest for names and URLs")
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    files = sorted(args.accepted.glob("*.json")) if args.accepted.is_dir() else [args.accepted]
    if not files:
        parser.error("No accepted version JSON files found")
    sources = source_index(args.source_manifest)
    project_ids = set()
    prepared = []
    for path in files:
        version = AcceptedProjectVersion.model_validate_json(path.read_text(encoding="utf-8-sig"))
        project = convert(version, sources)
        if project.project_id in project_ids:
            raise ValueError(f"duplicate project identity in accepted versions: {project.project_id}")
        project_ids.add(project.project_id)
        stem = re.sub(r"[^A-Za-z0-9._-]", "_", project.project_id).strip("._")[:80] or "project"
        digest = hashlib.sha256(project.project_id.encode()).hexdigest()[:8]
        output = args.output_dir / f"{stem}-{digest}.json"
        prepared.append((project, output))
    stale = set(args.output_dir.glob("*.json")) - {output for _, output in prepared}
    if stale:
        raise ValueError(f"output directory contains unlisted JSON files: {', '.join(str(path) for path in sorted(stale))}")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    exported = []
    for project, output in prepared:
        output.write_text(project.model_dump_json(indent=2) + "\n", encoding="utf-8")
        exported.append({"project_id": project.project_id, "file": str(output),
                         "is_fixture": project.is_fixture, "validation_state": project.validation_state.value,
                         "geometry_quality": project.geometry_quality.value})
    print(json.dumps({"exported": exported}, indent=2))


if __name__ == "__main__":
    main()
