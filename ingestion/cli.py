import argparse
import sys

from ingestion.common import IngestionError, encoded, read_json, write_json
from ingestion.geospatial.overpass import ENDPOINT, REGIONS, build_query
from ingestion.jobs.handoff import export_starter
from ingestion.jobs.pipeline import ingest
from ingestion.versioning.sources import ACCESS_CLASSES, Store


def load_artifact(store, version_id):
    source = next((s for s in store.versions() if s["source_version_id"] == version_id), None)
    jobs = [j for j in store.jobs() if j.get("source_version_id") == version_id and
            j["status"] in ("READY_FOR_INTELLIGENCE", "NEEDS_REVIEW") and "parsed_path" in j]
    if not source or not jobs:
        raise IngestionError("PARSED_SOURCE_NOT_FOUND", version_id)
    return source, read_json(store.root / jobs[-1]["parsed_path"])


def parser():
    root = argparse.ArgumentParser(description="SYNCHRO public source acquisition; all candidate associations remain unverified")
    root.add_argument("--data-dir", default="data", help="Local storage root (default: data)")
    commands = root.add_subparsers(dest="command", required=True)
    source = commands.add_parser("ingest", help="Preserve and parse a local file or public URL")
    location = source.add_mutually_exclusive_group(required=True)
    location.add_argument("--path")
    location.add_argument("--url")
    source.add_argument("--format", required=True, choices=["xlsx", "csv", "pdf", "docx", "html", "geojson", "shapefile"])
    for key in ("source-id", "title", "publisher", "source-type"):
        source.add_argument(f"--{key}", required=True)
    source.add_argument("--source-tier", choices=["A", "B", "C"], required=True)
    source.add_argument("--access-class", choices=ACCESS_CLASSES, required=True)
    source.add_argument("--utility")
    source.add_argument("--source-crs")
    source.add_argument("--force", action="store_true", help="Reparse an existing SourceVersion")
    starter = commands.add_parser("starter", help="Map a parsed workbook and export a portable Mac handoff")
    starter.add_argument("--source-version", required=True)
    starter.add_argument("--mapping", required=True)
    starter.add_argument("--geo-source-version", action="append", default=[])
    starter.add_argument("--supporting-source-version", action="append", default=[])
    challenge = commands.add_parser("challenge", help="Import the organizer workbook and available supporting documents")
    challenge.add_argument("--input-dir", required=True)
    challenge.add_argument("--include-osm", action="store_true", help="Filter existing OSM snapshots in this data directory")
    overpass = commands.add_parser("overpass", help="Download one bulk regional utility OSM snapshot")
    overpass.add_argument("--utility", choices=["DESC", "GPC"], required=True)
    overpass.add_argument("--region", choices=list(REGIONS), required=True)
    commands.add_parser("catalog", help="Export source and job metadata to catalog.json")
    commands.add_parser("demo", help="Run offline with two explicitly synthetic starter projects")
    return root


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        store = Store(args.data_dir)
        if args.command == "ingest":
            metadata = {key: getattr(args, key) for key in
                        ("source_id", "title", "publisher", "source_type", "source_tier", "access_class", "utility")}
            _, _, result = ingest(store, metadata=metadata, file_format=args.format,
                                  path=args.path, url=args.url, source_crs=args.source_crs, force=args.force)
        elif args.command == "starter":
            source, parsed = load_artifact(store, args.source_version)
            geospatial = [load_artifact(store, version) for version in args.geo_source_version]
            supporting = [load_artifact(store, version) for version in args.supporting_source_version]
            output, report = export_starter(store, source, parsed, read_json(args.mapping), geospatial, supporting)
            result = {"output_dir": str(output), "quality_report": report}
        elif args.command == "challenge":
            from ingestion.challenge import run_challenge
            result = run_challenge(store, args.input_dir, args.include_osm)
        elif args.command == "overpass":
            query = build_query(args.utility, args.region)
            metadata = {"source_id": f"OSM-{args.utility}-{args.region}", "title": f"{args.utility} {args.region} infrastructure",
                        "publisher": "OpenStreetMap contributors", "source_type": "OPENSTREETMAP", "source_tier": "B",
                        "access_class": "PUBLIC_CONFIRMED", "utility": args.utility,
                        "query_metadata": {"query_text": query, "bbox_south_west_north_east": REGIONS[args.region],
                                           "endpoint": ENDPOINT, "provider": "OPENSTREETMAP",
                                           "license": "ODbL", "attribution_url": "https://www.openstreetmap.org/copyright"}}
            _, _, result = ingest(store, metadata=metadata, file_format="overpass", url=ENDPOINT,
                                  method="POST", request_data={"data": query})
        elif args.command == "catalog":
            result = {"source_versions": store.versions(), "jobs": store.jobs()}
            write_json(store.root / "catalog.json", result)
        else:
            from ingestion.demo import run_demo
            result = run_demo(store)
        print(encoded(result), end="")
        return 0
    except Exception as exc:
        print(encoded({"status": "FAILED", "error_code": getattr(exc, "code", "COMMAND_FAILED"),
                       "message": str(exc), "retryable": getattr(exc, "retryable", False)}), file=sys.stderr, end="")
        return 1
