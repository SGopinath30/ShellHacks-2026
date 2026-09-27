"""Basic DOCX body text for source preservation; no rendering or semantic extraction."""
from io import BytesIO
from xml.etree import ElementTree
from zipfile import ZipFile

from ingestion.common import IngestionError

WORD = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def parse_docx(data):
    with ZipFile(BytesIO(data)) as archive:
        entry = archive.getinfo("word/document.xml")
        if entry.file_size > 20 * 1024 * 1024:
            raise IngestionError("DOCUMENT_TOO_LARGE", "DOCX body exceeds the 20 MiB limit")
        root = ElementTree.fromstring(archive.read(entry))
    paragraphs = []
    for number, paragraph in enumerate(root.iter(WORD + "p"), 1):
        text = "".join(node.text or "" for node in paragraph.iter(WORD + "t"))
        if text.strip():
            paragraphs.append({"paragraph_number": number, "text": text})
    return {"format": "docx", "paragraphs": paragraphs,
            "limitations": "Body text only, including table paragraphs. No pagination, images, headers, or OCR. Original DOCX retained."}
