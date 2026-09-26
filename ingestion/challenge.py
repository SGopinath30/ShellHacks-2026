"""Repeatable import of the supplied Sperry starter folder, with no network calls."""
import json
from importlib.resources import files
from pathlib import Path

from ingestion.common import IngestionError, digest, write_json
from ingestion.jobs.handoff import export_starter
from ingestion.jobs.pipeline import ingest

SUPPORTING = [
    ("CHALLENGE-GRIDLOCK", "ShellHacks_Challenge_Gridlock.docx", "docx", "CHALLENGE_DOCUMENT", "C", None, "Challenge organizers"),
    ("LOCATION-GUIDE", "Finding_Real_Locations_Guide.docx", "docx", "CHALLENGE_DOCUMENT", "C", None, "Challenge organizers"),
    ("DESC-2024-2028-PROJECTS", "Project Listings/Dominion Energy/2024-2028-2million-and-above-project-descriptions.pdf",
     "pdf", "UTILITY_PDF", "A", "DESC", "Dominion Energy South Carolina"),
    ("GPC-2025-IRP-V3", "Project Listings/Georgia Power/2025 IRP Volume 3 PUBLIC DISCLOSURE.pdf",
     "pdf", "UTILITY_PDF", "A", "GPC", "Georgia Power"),
]


def run_challenge(store, input_dir, include_osm=False):
    from ingestion.cli import load_artifact

    folder = Path(input_dir)
    workbook = folder / "Projects_Overlaps.xlsx"
    original_sha = digest(workbook.read_bytes())
    source, parsed, job = ingest(store, path=workbook, file_format="xlsx", metadata={
        "source_id": "STARTER-PROJECTS", "title": "Projects_Overlaps.xlsx", "publisher": "Challenge organizers",
        "source_type": "STARTER_WORKBOOK", "source_tier": "C", "access_class": "PUBLIC_ASSUMED",
        "access_basis": "User-supplied organizer starter package; public-source challenge policy",
        "distribution_origin": "STARTER_PACKAGE"})
    supporting, missing = [], []
    for source_id, relative, file_format, source_type, tier, utility, publisher in SUPPORTING:
        path = folder / relative
        if not path.exists():
            missing.append(relative)
            continue
        record, representation, _ = ingest(store, path=path, file_format=file_format, metadata={
            "source_id": source_id, "title": path.stem, "publisher": publisher,
            "source_type": source_type, "source_tier": tier, "utility": utility,
            "access_class": "PUBLIC_ASSUMED", "distribution_origin": "STARTER_PACKAGE",
            "access_basis": "Supplied in organizer starter folder; no independent public-access check",
            "supplied_relative_path": relative})
        supporting.append((record, representation))
    geospatial = []
    if include_osm:
        latest = {}
        for record in store.versions():
            if record["source_type"] == "OPENSTREETMAP":
                latest[record["source_id"]] = record
        for record in latest.values():
            geospatial.append(load_artifact(store, record["source_version_id"]))
    mapping = json.loads(files("ingestion.catalog").joinpath("sperry_starter_mapping.json").read_text(encoding="utf-8"))
    output, report = export_starter(store, source, parsed, mapping, geospatial, supporting)
    if digest(workbook.read_bytes()) != original_sha:
        raise IngestionError("INPUT_CHANGED", "Workbook changed during import")
    result = {"output_dir": str(output), "source_version_id": source["source_version_id"],
              "source_sha256": original_sha, "quality_report": report, "missing_supporting_files": missing,
              "workbook_job": job, "source_workbook_unchanged": True}
    write_json(store.root / "challenge_run.json", result)
    write_json(store.root / "catalog.json", {"source_versions": store.versions(), "jobs": store.jobs()})
    return result
