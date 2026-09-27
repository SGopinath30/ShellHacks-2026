"""Local, non-AI entry point for structured project-source ingestion."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from project_intelligence.contracts import SourceAccess, SourceArtifact, SourceType
from project_intelligence.extraction import parse_structured_source
from project_intelligence.validation import validate_candidate


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Parse a starter XLSX/CSV/JSON source without model inference."
    )
    parser.add_argument("path", type=Path)
    parser.add_argument("--source-version-id", required=True)
    parser.add_argument("--utility", required=True)
    parser.add_argument(
        "--source-access",
        choices=[item.value for item in SourceAccess],
        default=SourceAccess.UNKNOWN.value,
    )
    parser.add_argument("--source-url")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    source_path = args.path.resolve()
    source_type = _source_type(source_path)
    source_hash = hashlib.sha256(source_path.read_bytes()).hexdigest()
    source = SourceArtifact(
        source_version_id=args.source_version_id,
        source_type=source_type,
        utility=args.utility,
        path=str(source_path),
        source_url=args.source_url,
        downloaded_file_hash=source_hash,
        source_access=SourceAccess(args.source_access),
    )
    candidates = parse_structured_source(source)
    payload = {
        "source": source.model_dump(mode="json"),
        "candidate_count": len(candidates),
        "candidates": [item.model_dump(mode="json") for item in candidates],
        "validation": [
            validate_candidate(item).model_dump(mode="json") for item in candidates
        ],
    }
    rendered = json.dumps(payload, indent=2)
    if args.output:
        args.output.write_text(f"{rendered}\n", encoding="utf-8")
    else:
        print(rendered)


def _source_type(path: Path) -> SourceType:
    suffix = path.suffix.casefold()
    if suffix == ".xlsx":
        return SourceType.STARTER_WORKBOOK
    if suffix == ".csv":
        return SourceType.CSV
    if suffix == ".json":
        return SourceType.JSON
    raise ValueError("deterministic CLI supports only .xlsx, .csv, and .json")


if __name__ == "__main__":
    main()
