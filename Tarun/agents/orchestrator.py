"""Concurrent map/reduce orchestration for extraction and validation agents."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from collections.abc import Iterable
from functools import partial
from uuid import uuid4

from agents.extractor import ExtractorAgent
from agents.validator import ValidatorAgent
from extraction.errors import IngestionError
from extraction.models import DocumentChunk, ExtractionRun, ValidationResult


class ExtractionSwarm:
    """Fans chunks out to extraction workers, then validates every candidate."""

    def __init__(
        self,
        extractor: ExtractorAgent,
        validator: ValidatorAgent,
        *,
        max_workers: int = 4,
    ) -> None:
        if max_workers < 1:
            raise ValueError("max_workers must be positive")
        self.extractor = extractor
        self.validator = validator
        self.max_workers = max_workers

    def run(self, chunks: Iterable[DocumentChunk]) -> ExtractionRun:
        materialized = list(chunks)
        if not materialized:
            raise IngestionError("no parsed source elements were supplied")

        run_id = f"run-{uuid4()}"
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            batches = list(
                executor.map(partial(self.extractor.extract, run_id=run_id), materialized)
            )

        jobs = [
            (chunk, candidate, batch.audit)
            for chunk, batch in zip(materialized, batches, strict=True)
            for candidate in batch.projects
        ]
        results: list[ValidationResult] = []
        if jobs:
            with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                futures = [
                    executor.submit(self.validator.validate, chunk, candidate, audit)
                    for chunk, candidate, audit in jobs
                ]
                results = [future.result() for future in futures]

        return ExtractionRun(
            chunks_processed=len(materialized),
            candidates_found=len(jobs),
            results=results,
            manifests=[batch.manifest for batch in batches],
        )
