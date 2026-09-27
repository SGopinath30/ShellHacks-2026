"""Deterministic CSV and JSON project-row ingestion."""

from __future__ import annotations

import csv
import json
from pathlib import Path

from project_intelligence.contracts import SourceArtifact, SourceType
from project_intelligence.extraction.starter_workbook import (
    parse_starter_rows,
    parse_starter_workbook,
)


def parse_structured_source(source: SourceArtifact):
    if source.source_type is SourceType.STARTER_WORKBOOK:
        return parse_starter_workbook(source)
    path = Path(source.path)
    if source.source_type is SourceType.CSV:
        with path.open(encoding="utf-8-sig", newline="") as stream:
            rows = list(csv.DictReader(stream))
        return parse_starter_rows(rows, source=source, sheet=path.stem)
    if source.source_type is SourceType.JSON:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
        rows = payload if isinstance(payload, list) else [payload]
        if not all(isinstance(row, dict) for row in rows):
            raise ValueError("structured JSON project input must contain objects")
        return parse_starter_rows(rows, source=source, sheet=path.stem)
    raise ValueError(f"{source.source_type} is not a deterministic project-row source")
