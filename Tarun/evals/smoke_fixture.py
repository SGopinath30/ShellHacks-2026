"""Shared fixture loader for local and live Nemotron smoke tests."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from extraction.models import CandidateProject, DocumentChunk


FIXTURE_PATH = Path(__file__).parent / "fixtures" / "nemotron-smoke.json"


@dataclass(frozen=True, slots=True)
class NemotronSmokeFixture:
    chunk: DocumentChunk
    candidate: CandidateProject


def load_nemotron_smoke_fixture() -> NemotronSmokeFixture:
    payload = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    return NemotronSmokeFixture(
        chunk=DocumentChunk.model_validate(payload["chunk"]),
        candidate=CandidateProject.model_validate(payload["candidate"]),
    )
