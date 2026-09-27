"""FastAPI entry point for candidate project extraction."""

from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path
from threading import Lock
from typing import Literal, TypeVar

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from agents.extractor import ExtractorAgent
from agents.factory import create_swarm_from_env
from agents.orchestrator import ExtractionSwarm
from agents.validator import ValidatorAgent
from extraction.errors import IngestionError, ModelTransportError, StructuredOutputError
from extraction.models import (
    CandidateProject as ExtractionCandidateProject,
    CandidateProjectBatch,
    DocumentChunk,
    ExtractionRun,
    ProjectRecord,
    ProjectStatus,
    ProjectType,
    ValidationOutcome,
)
from project_intelligence.contracts import (
    CandidateProject as CanonicalCandidateProject,
    GeometryCandidate,
    GeometryValidation,
    ProjectReconciliationProposal,
    ProjectValidationResult,
    SourceAccess,
    VersionComparison,
)
from project_intelligence.source_safety import RestrictedSourceError


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
    source_access: SourceAccess = SourceAccess.UNKNOWN


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
    record_type: Literal["session_project"] = "session_project"
    name: str
    description: str
    status: ProjectStatus
    metadata: ProjectMetadata
    location: ProjectLocation


class VerifiedSourceMetadata(BaseModel):
    source_version_id: str
    utility_id: str
    title: str
    publisher: str
    source_url: str | None = None
    sha256: str
    publication_date: str | None = None
    source_access: SourceAccess
    access_basis: str | None = None


class SourceVerificationResponse(BaseModel):
    starter_project_id: str
    starter_candidate_id: str
    current_candidate_id: str
    source_match_score: float
    result: VersionComparison
    changed_fields: list[str]
    unresolved_fields: list[str]
    reconciliation: ProjectReconciliationProposal
    validation: ProjectValidationResult
    source_version_ids: list[str]


class GeometryStatusResponse(BaseModel):
    starter_project_id: str
    project_candidate_id: str
    dell_project_candidate_id: str
    geometry_source_version_id: str
    geometry_candidate: GeometryCandidate
    validation: GeometryValidation


class VerifiedProjectResponse(BaseModel):
    record_type: Literal["verified_candidate"] = "verified_candidate"
    candidate: CanonicalCandidateProject
    verification: SourceVerificationResponse
    sources: list[VerifiedSourceMetadata]
    geometry_statuses: list[GeometryStatusResponse]


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
    def __init__(self, candidate: ExtractionCandidateProject) -> None:
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


@app.post("/extract", response_model=ExtractionCandidateProject)
async def extract(
    candidate: ExtractionCandidateProject,
) -> ExtractionCandidateProject:
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
    except (IngestionError, RestrictedSourceError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except (ModelTransportError, StructuredOutputError) as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.get(
    "/api/projects",
    response_model=list[VerifiedProjectResponse | ProjectResponse],
)
def list_projects(
    request: Request,
) -> list[VerifiedProjectResponse | ProjectResponse]:
    """Return canonical verified candidates plus session-only API extractions."""
    try:
        verified = _verified_project_responses(request)
    except (OSError, ValueError, KeyError) as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Verified project artifacts are unavailable: {exc}",
        ) from exc
    session_records = [
        _project_response(record, mock_mode)
        for record, mock_mode in _project_store(request).all()
    ]
    return [*verified, *session_records]


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
        source_access=payload.source_access,
    )

    try:
        swarm = _production_swarm(request) if modal_enabled else _mock_swarm(payload.text)
        run = swarm.run([chunk])
    except (IngestionError, RestrictedSourceError, ValueError) as exc:
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


def _mock_candidate(source_text: str) -> ExtractionCandidateProject:
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

    return ExtractionCandidateProject(
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


def _verified_project_responses(request: Request) -> list[VerifiedProjectResponse]:
    phase_b_path = Path(
        getattr(
            request.app.state,
            "phase_b_source_verification_path",
            os.getenv(
                "PHASE_B_SOURCE_VERIFICATION_PATH",
                "data/derived/phase_b_source_verification.json",
            ),
        )
    )
    phase_c_path = Path(
        getattr(
            request.app.state,
            "phase_c_geometry_validation_path",
            os.getenv(
                "PHASE_C_GEOMETRY_VALIDATION_PATH",
                "data/derived/phase_c_geometry_validation.json",
            ),
        )
    )
    phase_b_exists = phase_b_path.is_file()
    phase_c_exists = phase_c_path.is_file()
    if not phase_b_exists and not phase_c_exists:
        return []
    if phase_b_exists != phase_c_exists:
        missing = phase_c_path if phase_b_exists else phase_b_path
        raise ValueError(f"required paired artifact is missing: {missing}")

    phase_b = json.loads(phase_b_path.read_text(encoding="utf-8"))
    phase_c = json.loads(phase_c_path.read_text(encoding="utf-8"))
    if phase_b.get("phase") != "B" or phase_c.get("phase") != "C":
        raise ValueError("project artifacts have invalid phase identifiers")

    candidates = [
        CanonicalCandidateProject.model_validate(item)
        for item in phase_b["current_candidates"]
    ]
    candidate_ids = [item.candidate_project_id for item in candidates]
    if len(candidate_ids) != len(set(candidate_ids)):
        raise ValueError("Phase B contains duplicate candidate project IDs")

    verifications = [
        SourceVerificationResponse.model_validate(item)
        for item in phase_b["verifications"]
    ]
    verification_by_id = {
        item.current_candidate_id: item for item in verifications
    }
    if len(verification_by_id) != len(verifications):
        raise ValueError("Phase B contains duplicate project verification IDs")
    if set(verification_by_id) != set(candidate_ids):
        raise ValueError(
            "Phase B candidates and source verifications are not one-to-one"
        )

    sources = [
        VerifiedSourceMetadata.model_validate(item) for item in phase_b["sources"]
    ]
    source_by_id = {item.source_version_id: item for item in sources}
    if len(source_by_id) != len(sources):
        raise ValueError("Phase B contains duplicate source version IDs")

    geometry_statuses = [
        GeometryStatusResponse.model_validate(item)
        for item in phase_c["geometry_validations"]
    ]
    geometry_by_project: dict[str, list[GeometryStatusResponse]] = {
        candidate_id: [] for candidate_id in candidate_ids
    }
    for item in geometry_statuses:
        if item.project_candidate_id not in geometry_by_project:
            raise ValueError(
                "Phase C geometry references an unknown Phase B candidate: "
                f"{item.project_candidate_id}"
            )
        if (
            item.geometry_candidate.project_candidate_id
            != item.project_candidate_id
        ):
            raise ValueError(
                "Phase C geometry candidate is linked to a different project"
            )
        geometry_by_project[item.project_candidate_id].append(item)

    responses = []
    for candidate in candidates:
        verification = verification_by_id[candidate.candidate_project_id]
        source_ids = set(verification.source_version_ids)
        missing_sources = source_ids - set(source_by_id)
        if missing_sources:
            raise ValueError(
                f"Phase B references missing sources: {sorted(missing_sources)}"
            )
        responses.append(
            VerifiedProjectResponse(
                candidate=candidate,
                verification=verification,
                sources=[
                    source_by_id[source_id]
                    for source_id in verification.source_version_ids
                ],
                geometry_statuses=geometry_by_project[candidate.candidate_project_id],
            )
        )
    return responses


def _env_flag(name: str, *, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.casefold() in {"1", "true", "yes", "on"}
