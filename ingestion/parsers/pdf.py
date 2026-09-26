from io import BytesIO

from pypdf import PdfReader

from ingestion.common import IngestionError


def parse_pdf(data):
    reader = PdfReader(BytesIO(data))
    if reader.is_encrypted:
        raise IngestionError("ENCRYPTED_PDF", "Encrypted PDFs require a public, unrestricted copy")
    pages = []
    for number, page in enumerate(reader.pages, 1):
        text = page.extract_text() or ""
        pages.append({"page_number": number, "text": text,
                      "status": "TEXT_EXTRACTED" if text.strip() else "OCR_REQUIRED"})
    return {"format": "pdf", "page_count": len(pages), "pages": pages,
            "status": "OCR_REQUIRED" if any(p["status"] == "OCR_REQUIRED" for p in pages) else "TEXT_EXTRACTED"}
