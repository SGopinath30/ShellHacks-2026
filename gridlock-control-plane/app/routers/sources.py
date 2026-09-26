from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(prefix="/sources", tags=["sources"])

# Stub -- owned jointly with the Dell/ingestion branch. This machine (Control
# Plane) just needs the route to exist so the frontend can integrate; actual
# upload/parsing lives in ingestion/.


@router.post("")
def register_source(source_id: str, source_name: str, source_url: str | None = None):
    """Register a source document (PDF/XLSX/CSV/GIS). Real implementation
    lives in the ingestion subsystem -- this is a placeholder so FastAPI
    exposes the contract from day one (PRD section 23)."""
    return {"source_id": source_id, "source_name": source_name, "status": "registered"}


@router.post("/{source_id}/ingest")
def ingest_source(source_id: str):
    """Trigger extraction + normalization for a registered source.
    Placeholder pending the extraction subsystem (M4 Mac / Swarms + Nemotron)."""
    return {"source_id": source_id, "status": "ingest_triggered"}
