import json

import pytest

from extraction.errors import ParsingError, SourceRetrievalError
from extraction.parsing import parse_bytes, parse_document


def test_text_parser_preserves_metadata_and_hash() -> None:
    chunks = parse_bytes(
        b"First paragraph.\n\nSecond paragraph.",
        filename="plan.txt",
        utility_id="utility-a",
        source_id="source-a",
        chunk_size=25,
        overlap=0,
    )

    assert [chunk.page_or_row for chunk in chunks] == ["text", "text:chunk-2"]
    assert all(chunk.source_id == "source-a" for chunk in chunks)
    assert all(chunk.document_hash for chunk in chunks)


def test_csv_parser_assigns_physical_row_numbers() -> None:
    chunks = parse_bytes(
        b"name,voltage\nNorth Ridge,115\nSouth Ridge,230\n",
        filename="projects.csv",
        utility_id="utility-a",
    )

    assert [chunk.page_or_row for chunk in chunks] == ["row:2", "row:3"]
    assert json.loads(chunks[0].content)["name"] == "North Ridge"


def test_parser_rejects_invalid_overlap() -> None:
    with pytest.raises(ValueError, match="overlap"):
        parse_bytes(
            b"content",
            filename="plan.txt",
            utility_id="utility-a",
            chunk_size=10,
            overlap=10,
        )


def test_fixed_parser_does_not_emit_overlap_only_tail() -> None:
    chunks = parse_bytes(
        b"abcdefghij",
        filename="plan.txt",
        utility_id="utility-a",
        chunk_size=10,
        overlap=2,
        strategy="fixed",
    )

    assert [chunk.content for chunk in chunks] == ["abcdefghij"]


def test_parser_rejects_empty_document_before_inference() -> None:
    with pytest.raises(ParsingError, match="no usable source elements"):
        parse_bytes(b"  \n\n", filename="empty.txt", utility_id="utility-a")


def test_parser_reports_missing_source_explicitly(tmp_path) -> None:
    with pytest.raises(SourceRetrievalError, match="failed to read source document"):
        parse_document(tmp_path / "missing.pdf", utility_id="utility-a")
