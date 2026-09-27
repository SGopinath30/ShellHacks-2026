import re
from typing import TypeVar

import pytest
from pydantic import BaseModel

from agents.extractor import ExtractorAgent
from agents.orchestrator import ExtractionSwarm
from agents.validator import ValidatorAgent
from evals.smoke_fixture import load_nemotron_smoke_fixture
from extraction.errors import IngestionError
from extraction.models import CandidateProjectBatch, DocumentChunk, ValidationOutcome


ResponseT = TypeVar("ResponseT", bound=BaseModel)


class FakeExtractorClient:
    def generate(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        response_model: type[ResponseT],
    ) -> ResponseT:
        payload = {
            "projects": [
                {
                    "project_name": "North Ridge Substation",
                    "status": "planned",
                    "location_text": "North Ridge",
                    "source_snippet": "North Ridge Substation is planned in North Ridge.",
                    "field_evidence": [
                        {
                            "field_name": "project_name",
                            "quoted_text": "North Ridge Substation",
                            "page_or_row": "page:1",
                        },
                        {
                            "field_name": "location_text",
                            "quoted_text": "North Ridge",
                            "page_or_row": "page:1",
                        },
                    ],
                    "extraction_confidence": 0.95,
                }
            ]
        }
        return response_model.model_validate(payload)


class FixtureExtractorClient:
    def generate(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        response_model: type[ResponseT],
    ) -> ResponseT:
        fixture = load_nemotron_smoke_fixture()
        return response_model.model_validate(
            {"projects": [fixture.candidate.model_dump(mode="json")]}
        )


class SourceAwareExtractorClient:
    def generate(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        response_model: type[ResponseT],
    ) -> ResponseT:
        voltage_match = re.search(r"new (\d+) kV substation", user_prompt)
        assert voltage_match is not None
        voltage = float(voltage_match.group(1))
        quote = f"new {voltage:g} kV substation"
        return response_model.model_validate(
            {
                "projects": [
                    {
                        "project_name": "North Ridge Substation",
                        "status": "planned",
                        "voltage_kv": voltage,
                        "location_text": "North Ridge",
                        "source_snippet": quote,
                        "field_evidence": [
                            {
                                "field_name": "project_name",
                                "quoted_text": "North Ridge Substation",
                                "page_or_row": "page:1",
                            },
                            {
                                "field_name": "voltage_kv",
                                "quoted_text": quote,
                                "page_or_row": "page:1",
                            },
                            {
                                "field_name": "location_text",
                                "quoted_text": "North Ridge",
                                "page_or_row": "page:1",
                            },
                        ],
                        "extraction_confidence": 0.9,
                    }
                ]
            }
        )


def test_swarm_extracts_and_validates_candidates() -> None:
    chunk = DocumentChunk(
        source_id="source-a",
        source_name="plan.txt",
        utility_id="utility-a",
        page_or_row="page:1",
        content="North Ridge Substation is planned in North Ridge.",
    )
    extractor = ExtractorAgent(
        FakeExtractorClient(),
        model="fake-model",
        provider="test-provider",
        mock_mode=True,
    )
    swarm = ExtractionSwarm(extractor, ValidatorAgent(), max_workers=2)

    run = swarm.run([chunk])

    assert run.chunks_processed == 1
    assert run.candidates_found == 1
    assert run.results[0].outcome is ValidationOutcome.CORRECTED
    assert run.results[0].record is not None
    assert run.results[0].record.start_date is None
    assert run.results[0].record.end_date is None


def test_swarm_rejects_empty_parsed_input() -> None:
    extractor = ExtractorAgent(
        FakeExtractorClient(), model="fake-model", provider="test-provider"
    )
    with pytest.raises(IngestionError, match="no parsed source elements"):
        ExtractionSwarm(extractor, ValidatorAgent()).run([])


def test_smoke_fixture_extracts_and_validates_with_mock_client() -> None:
    fixture = load_nemotron_smoke_fixture()
    extractor = ExtractorAgent(
        FixtureExtractorClient(),
        model="mock-nemotron",
        provider="test-provider",
        mock_mode=True,
    )

    run = ExtractionSwarm(extractor, ValidatorAgent(), max_workers=1).run([fixture.chunk])

    assert run.chunks_processed == 1
    assert run.candidates_found == 1
    assert len(run.results) == 1
    assert run.results[0].record is not None
    assert run.results[0].record.project_name == fixture.candidate.project_name
    assert run.results[0].record.project_type == fixture.candidate.project_type
    assert run.results[0].record.start_date == fixture.candidate.start_date
    assert run.manifests[0].source_id == fixture.chunk.source_id
    assert run.manifests[0].mock_mode is True
    assert run.manifests[0].cache_hit is False


def test_changed_source_voltage_changes_output_and_manifest_hash() -> None:
    base_content = (
        "North Ridge Substation is planned to add a new {voltage} kV substation in North Ridge."
    )
    chunks = [
        DocumentChunk(
            source_id=f"source-{voltage}",
            source_name="plan.txt",
            utility_id="utility-a",
            page_or_row="page:1",
            content=base_content.format(voltage=voltage),
        )
        for voltage in (115, 230)
    ]
    swarm = ExtractionSwarm(
        ExtractorAgent(
            SourceAwareExtractorClient(),
            model="mock-nemotron",
            provider="test-provider",
            mock_mode=True,
        ),
        ValidatorAgent(),
        max_workers=1,
    )

    first = swarm.run([chunks[0]])
    second = swarm.run([chunks[1]])

    assert first.results[0].record is not None
    assert second.results[0].record is not None
    assert first.results[0].record.voltage_kv == 115
    assert second.results[0].record.voltage_kv == 230
    assert first.manifests[0].input_content_hash != second.manifests[0].input_content_hash
    assert first.manifests[0].cache_hit is False
    assert second.manifests[0].cache_hit is False
