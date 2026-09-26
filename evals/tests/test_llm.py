import json

from pydantic import BaseModel

from evals.smoke_fixture import load_nemotron_smoke_fixture
from extraction.llm import NemotronClient, NemotronConfig
from extraction.models import CandidateProject, CandidateProjectBatch
from extraction.prompts import build_extraction_prompt


class ExampleResponse(BaseModel):
    value: str


class RecordingNemotronClient(NemotronClient):
    def __init__(self, config: NemotronConfig) -> None:
        super().__init__(config)
        self.payload: dict | None = None

    def _post_json(self, payload: dict) -> dict:
        self.payload = payload
        return {"choices": [{"message": {"content": '{"value":"ok"}'}}]}


def test_generate_bounds_output_and_disables_thinking() -> None:
    client = RecordingNemotronClient(
        NemotronConfig(base_url="https://example.test/v1", model="nemotron")
    )

    result = client.generate(
        system_prompt="Return JSON.",
        user_prompt="Extract a value.",
        response_model=ExampleResponse,
    )

    assert result == ExampleResponse(value="ok")
    assert client.payload is not None
    assert client.payload["temperature"] == 0.0
    assert client.payload["max_tokens"] == 4096
    assert client.payload["chat_template_kwargs"] == {"enable_thinking": False}


def test_generate_honors_reasoning_and_token_overrides() -> None:
    client = RecordingNemotronClient(
        NemotronConfig(
            base_url="https://example.test/v1",
            model="nemotron",
            max_tokens=512,
            repetition_penalty=1.15,
            stop=("\n\n\n", "}\n}"),
            enable_thinking=True,
            separate_reasoning=False,
        )
    )

    client.generate(
        system_prompt="Return JSON.",
        user_prompt="Extract a value.",
        response_model=ExampleResponse,
    )

    assert client.payload is not None
    assert client.payload["max_tokens"] == 512
    assert client.payload["repetition_penalty"] == 1.15
    assert client.payload["stop"] == ["\n\n\n", "}\n}"]
    assert client.payload["chat_template_kwargs"] == {"enable_thinking": True}
    assert client.payload["separate_reasoning"] is False


def test_generate_forces_greedy_decoding() -> None:
    client = RecordingNemotronClient(
        NemotronConfig(
            base_url="https://example.test/v1",
            model="nemotron",
            temperature=0.8,
        )
    )

    client.generate(
        system_prompt="Return JSON.",
        user_prompt="Extract a value.",
        response_model=ExampleResponse,
    )

    assert client.payload is not None
    assert client.payload["temperature"] == 0.0


class PrefillNemotronClient(NemotronClient):
    def _post_json(self, payload: dict) -> dict:
        self.payload = payload
        return {"choices": [{"message": {"content": '"ok"}'}}]}


def test_generate_prefills_and_restores_response_prefix() -> None:
    client = PrefillNemotronClient(
        NemotronConfig(
            base_url="https://example.test/v1",
            model="nemotron",
            response_prefix='{"value":',
        )
    )

    result = client.generate(
        system_prompt="Return JSON.",
        user_prompt="Extract a value.",
        response_model=ExampleResponse,
    )

    assert result == ExampleResponse(value="ok")
    assert client.payload["messages"][-1] == {
        "role": "assistant",
        "content": '{"value":',
    }
    assert client.payload["continue_final_message"] is True


class CompletePrefillNemotronClient(NemotronClient):
    def _post_json(self, payload: dict) -> dict:
        self.payload = payload
        return {"choices": [{"message": {"content": '{"value":"ok"}'}}]}


def test_generate_does_not_duplicate_prefill_when_server_returns_complete_json() -> None:
    client = CompletePrefillNemotronClient(
        NemotronConfig(
            base_url="https://example.test/v1",
            model="nemotron",
            response_prefix='{"value":',
        )
    )

    result = client.generate(
        system_prompt="Return JSON.",
        user_prompt="Extract a value.",
        response_model=ExampleResponse,
    )

    assert result == ExampleResponse(value="ok")


def test_generate_anchors_project_name_in_strict_schema() -> None:
    fixture = load_nemotron_smoke_fixture()
    client = FixtureNemotronClient(
        NemotronConfig(
            base_url="https://example.test/v1",
            model="nemotron",
            project_name_anchor=fixture.candidate.project_name,
        )
    )

    client.generate(
        system_prompt="Return the project.",
        user_prompt="Extract the project.",
        response_model=CandidateProjectBatch,
    )

    schema = client.payload["response_format"]["json_schema"]["schema"]
    candidate_schema = schema["$defs"]["CandidateProject"]
    assert candidate_schema["properties"]["name"] == {
        "const": "North Ridge Substation Project",
        "type": "string",
    }
    assert set(candidate_schema["required"]) == {"name", "description", "status"}
    assert "geometry" not in candidate_schema["properties"]
    assert "source_id" not in candidate_schema["properties"]
    assert "source_page_row" not in candidate_schema["properties"]


def test_generate_constrains_extractive_values_to_source_text() -> None:
    fixture = load_nemotron_smoke_fixture()
    client = FixtureNemotronClient(
        NemotronConfig(base_url="https://example.test/v1", model="nemotron")
    )

    client.generate(
        system_prompt="Return the project.",
        user_prompt=build_extraction_prompt(fixture.chunk),
        response_model=CandidateProjectBatch,
    )

    schema = client.payload["response_format"]["json_schema"]["schema"]
    candidate_properties = schema["$defs"]["CandidateProject"]["properties"]
    evidence_properties = schema["$defs"]["FieldEvidence"]["properties"]
    assert candidate_properties["status"]["enum"] == ["approved"]
    assert fixture.candidate.source_snippet in candidate_properties["description"]["enum"]
    assert evidence_properties["field_name"]["enum"] == [
        "project_name",
        "project_type",
        "voltage_kv",
        "start_date",
        "end_date",
        "status",
        "location_text",
    ]


class MisclassifiedNemotronClient(NemotronClient):
    def _post_json(self, payload: dict) -> dict:
        return {
            "choices": [
                {
                    "message": {
                        "content": None,
                        "reasoning_content": '{"value":"ok"}',
                    }
                }
            ]
        }


def test_generate_accepts_misclassified_non_thinking_content() -> None:
    client = MisclassifiedNemotronClient(
        NemotronConfig(base_url="https://example.test/v1", model="nemotron")
    )

    result = client.generate(
        system_prompt="Return JSON.",
        user_prompt="Extract a value.",
        response_model=ExampleResponse,
    )

    assert result == ExampleResponse(value="ok")


class FixtureNemotronClient(NemotronClient):
    def _post_json(self, payload: dict) -> dict:
        self.payload = payload
        fixture = load_nemotron_smoke_fixture()
        content = json.dumps(
            {"projects": [fixture.candidate.model_dump(mode="json", by_alias=True)]},
            separators=(",", ":"),
        )
        return {"choices": [{"message": {"content": content}}]}


def test_generate_logs_and_parses_nonempty_candidate_batch(capsys) -> None:
    client = FixtureNemotronClient(
        NemotronConfig(
            base_url="https://example.test/v1",
            model="nemotron",
            log_raw_response=True,
        )
    )

    result = client.generate(
        system_prompt="Return the project.",
        user_prompt="Extract the project.",
        response_model=CandidateProjectBatch,
    )

    output = capsys.readouterr().out
    assert len(result.projects) == 1
    assert result.projects[0].project_name == "North Ridge Substation Project"
    assert "--- NEMOTRON_RAW_CONTENT BEGIN ---" in output
    assert '"projects":[{"name":"North Ridge Substation Project"' in output
    assert "--- NEMOTRON_RAW_CONTENT END ---" in output


class FakeHTTPResponse:
    def __init__(self, body: str) -> None:
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        return None

    def read(self) -> bytes:
        return self.body.encode()


def test_generate_logs_and_saves_exact_request_payload(monkeypatch, tmp_path, capsys) -> None:
    response_body = '{"choices":[{"message":{"content":"{\\"value\\":\\"ok\\"}"}}]}'
    monkeypatch.setattr(
        "extraction.llm.urlopen",
        lambda request, timeout: FakeHTTPResponse(response_body),
    )
    client = NemotronClient(
        NemotronConfig(
            base_url="https://example.test/v1",
            model="nemotron",
            log_request_payload=True,
            log_raw_response=True,
            diagnostic_log_dir=str(tmp_path),
        )
    )

    result = client.generate(
        system_prompt="Use source evidence only.",
        user_prompt="SOURCE_ELEMENTS: []",
        response_model=ExampleResponse,
    )

    output = capsys.readouterr().out
    request_files = list(tmp_path.glob("*-request.json"))
    response_files = list(tmp_path.glob("*-response.json"))
    assert result == ExampleResponse(value="ok")
    assert "--- NEMOTRON_REQUEST_PAYLOAD BEGIN ---" in output
    assert len(request_files) == 1
    assert len(response_files) == 1
    assert json.loads(request_files[0].read_text())["messages"][1]["content"] == (
        "SOURCE_ELEMENTS: []"
    )
    assert response_files[0].read_text() == response_body
