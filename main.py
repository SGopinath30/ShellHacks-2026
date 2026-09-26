"""FastAPI entry point for candidate project extraction."""

from __future__ import annotations

import hashlib
import os
import re
from threading import Lock
from typing import TypeVar

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from agents.extractor import ExtractorAgent
from agents.factory import create_swarm_from_env
from agents.orchestrator import ExtractionSwarm
from agents.validator import ValidatorAgent
from extraction.errors import IngestionError, ModelTransportError, StructuredOutputError
from extraction.models import (
    CandidateProject,
    CandidateProjectBatch,
    DocumentChunk,
    ExtractionRun,
    ProjectRecord,
    ProjectStatus,
    ProjectType,
    ValidationOutcome,
)


app = FastAPI(title="GridLock Extraction API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ExtractRequest(BaseModel):
    text: str = Field(min_length=1)


class ProjectMetadata(BaseModel):
    project_id: str
    utility_id: str
    source_id: str
    element_id: str
    extraction_confidence: float
    model: str
    mock_mode: bool


class ProjectLocation(BaseModel):
    text: str | None = None
    geometry: dict | None = None


class ProjectResponse(BaseModel):
    name: str
    description: str
    status: ProjectStatus
    metadata: ProjectMetadata
    location: ProjectLocation


class ElementEvidence(BaseModel):
    source_id: str
    source_name: str
    element_id: str
    text: str
    source_url: str | None = None


class ExtractionResponse(BaseModel):
    project: ProjectResponse
    validation_status: ValidationOutcome
    evidence: list[ElementEvidence]
    mock_mode: bool


class InMemoryProjectStore:
    def __init__(self) -> None:
        self._records: dict[str, tuple[ProjectRecord, bool]] = {}
        self._lock = Lock()

    def upsert(self, record: ProjectRecord, *, mock_mode: bool) -> None:
        with self._lock:
            self._records[record.project_id] = (record, mock_mode)

    def all(self) -> list[tuple[ProjectRecord, bool]]:
        with self._lock:
            return list(self._records.values())


ResponseT = TypeVar("ResponseT", bound=BaseModel)


class LocalMockExtractionClient:
    def __init__(self, candidate: CandidateProject) -> None:
        self.candidate = candidate

    def generate(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        response_model: type[ResponseT],
    ) -> ResponseT:
        return response_model.model_validate(
            {
                "projects": [
                    self.candidate.model_dump(mode="json", by_alias=True)
                ]
            }
        )


app.state.project_store = InMemoryProjectStore()


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


@app.get("/api/projects", response_model=list[ProjectResponse])
def list_projects(request: Request) -> list[ProjectResponse]:
    """Return validated records persisted by this API process."""
    store = _project_store(request)
    return [_project_response(record, mock_mode) for record, mock_mode in store.all()]


@app.post("/api/extract", response_model=ExtractionResponse)
def extract_text(
    payload: ExtractRequest,
    request: Request,
    use_modal_inference: bool | None = Query(default=None),
) -> ExtractionResponse:
    """Extract and deterministically validate one project-bearing text fragment."""
    modal_enabled = (
        _env_flag("USE_MODAL_INFERENCE", default=False)
        if use_modal_inference is None
        else use_modal_inference
    )
    source_hash = hashlib.sha256(payload.text.encode()).hexdigest()
    chunk = DocumentChunk(
        source_id=f"api-{source_hash[:16]}",
        source_name="api-request.txt",
        utility_id="api-user",
        page_or_row="element:1",
        content=payload.text,
        document_hash=source_hash,
        metadata={"parser_version": "api-direct-input", "parsed_element_count": 1},
    )

    try:
        swarm = _production_swarm(request) if modal_enabled else _mock_swarm(payload.text)
        run = swarm.run([chunk])
    except (IngestionError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except (ModelTransportError, StructuredOutputError) as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    validated = next(
        (result for result in run.results if result.record is not None),
        None,
    )
    if validated is None or validated.record is None:
        issues = [
            issue.model_dump(mode="json")
            for result in run.results
            for issue in result.issues
        ]
        raise HTTPException(
            status_code=422,
            detail={"message": "No validated project record was produced", "issues": issues},
        )

    record = validated.record
    mock_mode = bool(run.manifests and run.manifests[0].mock_mode)
    _project_store(request).upsert(record, mock_mode=mock_mode)
    return ExtractionResponse(
        project=_project_response(record, mock_mode),
        validation_status=validated.outcome,
        evidence=[
            ElementEvidence(
                source_id=item.source_id,
                source_name=item.source_name,
                element_id=item.page_or_row,
                text=item.snippet,
                source_url=str(item.source_url) if item.source_url else None,
            )
            for item in record.evidence
        ],
        mock_mode=mock_mode,
    )


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


def _project_store(request: Request) -> InMemoryProjectStore:
    store = getattr(request.app.state, "project_store", None)
    if store is None:
        store = InMemoryProjectStore()
        request.app.state.project_store = store
    return store


def _production_swarm(request: Request) -> ExtractionSwarm:
    swarm: ExtractionSwarm | None = getattr(
        request.app.state, "api_extraction_swarm", None
    )
    if swarm is None:
        swarm = create_swarm_from_env()
        request.app.state.api_extraction_swarm = swarm
    return swarm


def _mock_swarm(source_text: str) -> ExtractionSwarm:
    candidate = _mock_candidate(source_text)
    extractor = ExtractorAgent(
        LocalMockExtractionClient(candidate),
        model="local-deterministic-fixture",
        provider="local-mock",
        mock_mode=True,
    )
    return ExtractionSwarm(extractor, ValidatorAgent(), max_workers=1)


def _mock_candidate(source_text: str) -> CandidateProject:
    status_match = re.search(r"\b(approved|planned|proposed)\b", source_text)
    if status_match is None:
        raise ValueError(
            "Mock extraction requires one canonical status: approved, planned, or proposed"
        )
    status = status_match.group(1)
    description = next(
        (
            sentence.strip()
            for sentence in re.split(r"(?<=[.!?])\s+", source_text)
            if status in sentence
        ),
        source_text.strip(),
    )
    asset = (
        r"[A-Z][A-Za-z0-9&'’/() -]{1,160}?"
        r"(?:Substation(?: Project)?|Transmission Line(?: Project)?|"
        r"Transformer(?: Project)?|Facility(?: Project)?|Project)"
    )
    name_patterns = (
        rf"\b{status}\b\s+(?:the\s+|a\s+|an\s+)?(?P<name>{asset})",
        rf"(?P<name>{asset})\s+(?:is|was|has been)\s+{status}\b",
        rf"(?P<name>{asset})",
    )
    name = next(
        (
            match.group("name").strip()
            for pattern in name_patterns
            if (match := re.search(pattern, description)) is not None
        ),
        None,
    )
    if name is None:
        raise ValueError(
            "Mock extraction could not identify a named utility project in the text"
        )

    location_match = re.search(
        r"\bat\s+(?P<location>\d{1,6}\s+[^.]+)", source_text
    )
    lowered = source_text.casefold()
    if "substation" in lowered:
        project_type = ProjectType.SUBSTATION
    elif "transmission line" in lowered:
        project_type = ProjectType.TRANSMISSION_LINE
    elif "transformer" in lowered:
        project_type = ProjectType.TRANSFORMER
    else:
        project_type = ProjectType.UNKNOWN

    return CandidateProject(
        name=name,
        description=description,
        status=status,
        project_type=project_type,
        location_text=(
            location_match.group("location").strip() if location_match else None
        ),
        extraction_confidence=1.0,
    )


def _project_response(record: ProjectRecord, mock_mode: bool) -> ProjectResponse:
    geometry = record.geometry.geojson if record.geometry else None
    return ProjectResponse(
        name=record.project_name,
        description=record.source_snippet or record.evidence[0].snippet,
        status=record.status,
        metadata=ProjectMetadata(
            project_id=record.project_id,
            utility_id=record.utility_id,
            source_id=record.source_id,
            element_id=record.source_page_row,
            extraction_confidence=record.extraction_confidence,
            model=record.audit.model,
            mock_mode=mock_mode,
        ),
        location=ProjectLocation(text=record.location_text, geometry=geometry),
    )


def _env_flag(name: str, *, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.casefold() in {"1", "true", "yes", "on"}
