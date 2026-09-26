"""FastAPI entry point for candidate project extraction."""

from fastapi import FastAPI, HTTPException, Request

from agents.factory import create_swarm_from_env
from agents.orchestrator import ExtractionSwarm
from extraction.errors import IngestionError, ModelTransportError, StructuredOutputError
from extraction.models import CandidateProject, DocumentChunk, ExtractionRun


app = FastAPI(title="GridLock Extraction API", version="0.1.0")


@app.post("/extract", response_model=CandidateProject)
async def extract(candidate: CandidateProject) -> CandidateProject:
    """Validate and return an extracted candidate project."""
    return candidate


@app.post("/extract/document", response_model=ExtractionRun)
def extract_document(chunk: DocumentChunk, request: Request) -> ExtractionRun:
    """Run extractor and validator agents for one evidence-addressable chunk."""
    swarm: ExtractionSwarm | None = getattr(request.app.state, "extraction_swarm", None)
    if swarm is None:
        try:
            swarm = create_swarm_from_env()
        except (RuntimeError, ValueError) as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        request.app.state.extraction_swarm = swarm
    try:
        return swarm.run([chunk])
    except IngestionError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except (ModelTransportError, StructuredOutputError) as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
