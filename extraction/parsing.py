"""Deterministic document-to-``DocumentChunk`` adapters.

The parsers intentionally preserve source text and location labels.  They do not
try to identify projects; that remains the extractor agent's responsibility.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import re
from pathlib import Path
from typing import Iterable, Literal

from extraction.errors import ParsingError, SourceRetrievalError
from extraction.models import DocumentChunk
from project_intelligence.contracts import SourceAccess


ChunkStrategy = Literal["paragraph", "fixed"]
SUPPORTED_SUFFIXES = {".csv", ".json", ".md", ".pdf", ".txt", ".docx"}
PARSER_VERSION = "gridlock-parser-1.0.0"


def parse_document(
    path: str | Path,
    *,
    utility_id: str,
    source_id: str | None = None,
    source_url: str | None = None,
    source_access: SourceAccess = SourceAccess.UNKNOWN,
    chunk_size: int = 4_000,
    overlap: int = 200,
    strategy: ChunkStrategy = "paragraph",
) -> list[DocumentChunk]:
    """Parse a supported local document into evidence-addressable chunks."""

    document_path = Path(path)
    try:
        data = document_path.read_bytes()
    except OSError as exc:
        raise SourceRetrievalError(f"failed to read source document: {document_path}") from exc
    return parse_bytes(
        data,
        filename=document_path.name,
        utility_id=utility_id,
        source_id=source_id,
        source_url=source_url,
        source_access=source_access,
        chunk_size=chunk_size,
        overlap=overlap,
        strategy=strategy,
    )


def parse_bytes(
    data: bytes,
    *,
    filename: str,
    utility_id: str,
    source_id: str | None = None,
    source_url: str | None = None,
    source_access: SourceAccess = SourceAccess.UNKNOWN,
    chunk_size: int = 4_000,
    overlap: int = 200,
    strategy: ChunkStrategy = "paragraph",
) -> list[DocumentChunk]:
    """Parse in-memory document bytes.

    PDF and DOCX support are optional so lightweight deployments can still use
    text, Markdown, CSV, and JSON without installing document libraries.
    """

    if chunk_size < 1:
        raise ValueError("chunk_size must be positive")
    if overlap < 0 or overlap >= chunk_size:
        raise ValueError("overlap must be non-negative and smaller than chunk_size")
    if strategy not in {"paragraph", "fixed"}:
        raise ValueError(f"unsupported chunk strategy: {strategy}")

    suffix = Path(filename).suffix.lower()
    if suffix not in SUPPORTED_SUFFIXES:
        raise ValueError(f"unsupported document type: {suffix or '<none>'}")

    document_hash = hashlib.sha256(data).hexdigest()
    resolved_source_id = source_id or f"doc-{document_hash[:16]}"
    sections = _extract_sections(data, suffix)
    chunks: list[DocumentChunk] = []

    for location, text in sections:
        for index, content in enumerate(
            _chunk_text(text, chunk_size=chunk_size, overlap=overlap, strategy=strategy),
            start=1,
        ):
            location_label = location if index == 1 else f"{location}:chunk-{index}"
            chunks.append(
                DocumentChunk(
                    source_id=resolved_source_id,
                    source_name=filename,
                    utility_id=utility_id,
                    page_or_row=location_label,
                    content=content,
                    source_url=source_url,
                    document_hash=document_hash,
                    source_access=source_access,
                    metadata={"parser": suffix.lstrip("."), "chunk_strategy": strategy},
                )
            )
    if not chunks:
        raise ParsingError(f"{filename} produced no usable source elements")

    parsed_element_count = len(chunks)
    return [
        chunk.model_copy(
            update={
                "metadata": {
                    **chunk.metadata,
                    "parser_version": PARSER_VERSION,
                    "parsed_element_count": parsed_element_count,
                }
            }
        )
        for chunk in chunks
    ]


def _extract_sections(data: bytes, suffix: str) -> list[tuple[str, str]]:
    if suffix in {".txt", ".md"}:
        return [("text", data.decode("utf-8-sig"))]
    if suffix == ".csv":
        reader = csv.DictReader(io.StringIO(data.decode("utf-8-sig")))
        return [
            (f"row:{row_number}", json.dumps(row, ensure_ascii=False, sort_keys=True))
            for row_number, row in enumerate(reader, start=2)
        ]
    if suffix == ".json":
        payload = json.loads(data.decode("utf-8-sig"))
        rows = payload if isinstance(payload, list) else [payload]
        return [
            (f"item:{index}", json.dumps(row, ensure_ascii=False, sort_keys=True))
            for index, row in enumerate(rows, start=1)
        ]
    if suffix == ".pdf":
        try:
            from pypdf import PdfReader
        except ImportError as exc:  # pragma: no cover - environment-dependent
            raise RuntimeError("PDF parsing requires the 'documents' dependency group") from exc
        reader = PdfReader(io.BytesIO(data))
        return [
            (f"page:{page_number}", page.extract_text() or "")
            for page_number, page in enumerate(reader.pages, start=1)
        ]
    if suffix == ".docx":
        try:
            from docx import Document
        except ImportError as exc:  # pragma: no cover - environment-dependent
            raise RuntimeError("DOCX parsing requires the 'documents' dependency group") from exc
        document = Document(io.BytesIO(data))
        return [("document", "\n\n".join(p.text for p in document.paragraphs if p.text.strip()))]
    raise AssertionError(f"unhandled suffix: {suffix}")


def _chunk_text(
    text: str,
    *,
    chunk_size: int,
    overlap: int,
    strategy: ChunkStrategy,
) -> Iterable[str]:
    normalized = text.replace("\r\n", "\n").strip()
    if not normalized:
        return

    if strategy == "fixed":
        step = chunk_size - overlap
        start = 0
        while start < len(normalized):
            end = min(start + chunk_size, len(normalized))
            chunk = normalized[start:end].strip()
            if chunk:
                yield chunk
            if end == len(normalized):
                break
            start += step
        return

    paragraphs = [part.strip() for part in re.split(r"\n\s*\n", normalized) if part.strip()]
    current = ""
    for paragraph in paragraphs:
        if len(paragraph) > chunk_size:
            if current:
                yield current
                current = ""
            yield from _chunk_text(
                paragraph,
                chunk_size=chunk_size,
                overlap=overlap,
                strategy="fixed",
            )
            continue
        combined = f"{current}\n\n{paragraph}" if current else paragraph
        if len(combined) <= chunk_size:
            current = combined
        else:
            yield current
            prefix = current[-overlap:].lstrip() if overlap else ""
            overlapped = f"{prefix}\n\n{paragraph}" if prefix else paragraph
            current = overlapped if len(overlapped) <= chunk_size else paragraph
    if current:
        yield current
