import pytest
from pydantic import ValidationError

from evals.smoke_fixture import load_nemotron_smoke_fixture
from extraction.models import CandidateProjectBatch
from extraction.prompts import EXTRACTOR_SYSTEM_PROMPT, build_extraction_prompt


def test_extraction_prompt_uses_only_source_elements_as_evidence() -> None:
    fixture = load_nemotron_smoke_fixture()

    prompt = build_extraction_prompt(fixture.chunk)
    normalized_system_prompt = " ".join(EXTRACTOR_SYSTEM_PROMPT.split())

    assert "Schema descriptions are not source evidence" in normalized_system_prompt
    assert "East Junction" not in EXTRACTOR_SYSTEM_PROMPT
    assert "North Ridge" not in EXTRACTOR_SYSTEM_PROMPT
    assert "SOURCE_ELEMENTS" in prompt
    assert '"element_id":"project:1"' in prompt
    assert fixture.chunk.content in prompt
    assert "Return at least one valid project record" in prompt
    assert "projects array must contain at least one valid project" in prompt
    assert "compact, single-line, minified JSON" in EXTRACTOR_SYSTEM_PROMPT
    assert "Every value MUST be an exact verbatim substring" in EXTRACTOR_SYSTEM_PROMPT
    assert '["name", "description", "status"]' in EXTRACTOR_SYSTEM_PROMPT
    assert '["approved", "planned", "proposed"]' in EXTRACTOR_SYSTEM_PROMPT
    assert '"Project Name"' in EXTRACTOR_SYSTEM_PROMPT
    assert '"Voltage (KV)"' in EXTRACTOR_SYSTEM_PROMPT
    assert "no markdown" in prompt
    assert '\n  "source_id"' not in prompt


def test_candidate_batch_requires_nonempty_projects() -> None:
    schema = CandidateProjectBatch.model_json_schema()
    candidate_schema = schema["$defs"]["CandidateProject"]

    assert "projects" in schema["required"]
    assert schema["properties"]["projects"]["minItems"] == 1
    assert set(candidate_schema["required"]) == {"name", "description", "status"}
    assert "geometry" not in candidate_schema["properties"]
    assert "source_id" not in candidate_schema["properties"]
    assert "source_page_row" not in candidate_schema["properties"]
    with pytest.raises(ValidationError):
        CandidateProjectBatch.model_validate({})
    with pytest.raises(ValidationError):
        CandidateProjectBatch.model_validate({"projects": []})
