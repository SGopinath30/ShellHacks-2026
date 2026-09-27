"""Candidate extraction agent."""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Protocol, TypeVar
from uuid import uuid4

from pydantic import BaseModel

from extraction.models import (
    CandidateProjectBatch,
    DocumentChunk,
    ExtractionAudit,
    ExtractionBatch,
    ExtractionManifest,
)
from extraction.prompts import (
    EXTRACTION_PROMPT_VERSION,
    EXTRACTOR_SYSTEM_PROMPT,
    build_extraction_prompt,
)
from project_intelligence.source_safety import ensure_remote_inference_allowed


ResponseT = TypeVar("ResponseT", bound=BaseModel)
CANDIDATE_SCHEMA_VERSION = "candidate-project-1.0.0"


class StructuredClient(Protocol):
    def generate(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        response_model: type[ResponseT],
    ) -> ResponseT: ...


class ExtractorAgent:
    """Runs structured candidate extraction for one source chunk."""

    def __init__(
        self,
        client: StructuredClient,
        *,
        model: str,
        provider: str,
        model_version: str | None = None,
        mock_mode: bool = False,
    ) -> None:
        self.client = client
        self.model = model
        self.provider = provider
        self.model_version = model_version
        self.mock_mode = mock_mode

    def extract(self, chunk: DocumentChunk, *, run_id: str | None = None) -> ExtractionBatch:
        resolved_run_id = run_id or f"run-{uuid4()}"
        if not self.mock_mode:
            ensure_remote_inference_allowed(chunk.source_access)
        response = self.client.generate(
            system_prompt=EXTRACTOR_SYSTEM_PROMPT,
            user_prompt=build_extraction_prompt(chunk),
            response_model=CandidateProjectBatch,
        )
        audit = ExtractionAudit(
            model=self.model,
            model_version=self.model_version,
            provider=self.provider,
            extracted_at=datetime.now(timezone.utc),
            prompt_version=EXTRACTION_PROMPT_VERSION,
        )
        manifest = ExtractionManifest(
            run_id=resolved_run_id,
            source_id=chunk.source_id,
            source_url=chunk.source_url,
            downloaded_file_hash=chunk.document_hash,
            parser_version=str(chunk.metadata.get("parser_version", "direct-input")),
            parsed_element_count=int(chunk.metadata.get("parsed_element_count", 1)),
            selected_page_or_row_ids=[chunk.page_or_row],
            input_content_hash=hashlib.sha256(chunk.content.encode()).hexdigest(),
            model_id=self.model,
            prompt_version=EXTRACTION_PROMPT_VERSION,
            schema_version=CANDIDATE_SCHEMA_VERSION,
            cache_hit=False,
            mock_mode=self.mock_mode,
        )
        return ExtractionBatch(projects=response.projects, audit=audit, manifest=manifest)
