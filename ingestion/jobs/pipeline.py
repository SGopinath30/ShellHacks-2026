import json
import mimetypes
import uuid
from pathlib import Path

from ingestion import __version__
from ingestion.common import IngestionError, now, read_json, stable_id, write_json
from ingestion.downloaders.http import MAX_BYTES, fetch
from ingestion.parsers import parse
from ingestion.versioning.sources import check_access


def ingest(store, *, metadata, file_format, path=None, url=None, source_crs=None,
           force=False, method="GET", request_data=None):
    job = {"job_id": f"JOB-{uuid.uuid4().hex}", "source_id": metadata.get("source_id"),
           "created_at": now(), "history": []}

    def transition(status):
        job.update(status=status, updated_at=now())
        job["history"].append({"status": status, "at": job["updated_at"]})
        store.save_job(job)

    transition("DISCOVERED")
    try:
        check_access(metadata["access_class"])
        if bool(path) == bool(url):
            raise IngestionError("INPUT_REQUIRED", "Specify exactly one local path or public URL")
        transition("DOWNLOADING")
        if path:
            path = Path(path)
            if path.stat().st_size > MAX_BYTES:
                raise IngestionError("SOURCE_TOO_LARGE", "Source exceeds the 100 MiB v0 limit")
            data = path.read_bytes()
            transport = {"original_filename": path.name,
                         "mime_type": mimetypes.guess_type(path.name)[0] or "application/octet-stream"}
        else:
            data, transport = fetch(url, method=method, data=request_data)
        source, duplicate = store.preserve(data, {**metadata, **transport, "file_format": file_format})
        job["source_version_id"] = source["source_version_id"]
        job["disposition"] = "DUPLICATE_SOURCE_VERSION" if duplicate else "NEW_SOURCE_VERSION"
        transition("DOWNLOADED")
        parser_config = {"parser_version": __version__, "format": file_format, "source_crs": source_crs}
        artifact = Path("parsed") / source["source_version_id"] / stable_id("PARSE", parser_config)
        output = store.root / artifact / "parsed.json"
        if output.exists() and not force:
            parsed = read_json(output)
            job["parse_cached"] = True
        else:
            transition("PARSING")
            if file_format == "overpass":
                from ingestion.geospatial.overpass import convert_response
                parsed = convert_response(json.loads(data))
            else:
                parsed = parse(data, file_format, source_crs)
            write_json(output, parsed)
            job["parse_cached"] = False
        write_json(output.parent / "source_version.json", source)
        write_json(output.parent / "parser_config.json", parser_config)
        if "geojson" in parsed:
            write_json(store.root / "geo" / source["source_version_id"] / artifact.name / "features.geojson", parsed["geojson"])
        job["parsed_path"] = output.relative_to(store.root).as_posix()
        transition("PARSED")
        transition("NEEDS_REVIEW" if source["access_class"] == "ACCESS_UNCLEAR" else "READY_FOR_INTELLIGENCE")
        return source, parsed, job
    except Exception as exc:
        job["error"] = {"error_code": getattr(exc, "code", "INGESTION_FAILED"),
                        "message": str(exc), "retryable": getattr(exc, "retryable", False)}
        transition("FAILED")
        raise
