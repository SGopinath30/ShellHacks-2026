"""Small OpenAI-compatible client for a vLLM-hosted Nemotron endpoint."""

from __future__ import annotations

import hashlib
import json
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import TypeVar
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from pydantic import BaseModel, ValidationError

from extraction.errors import ModelTransportError, StructuredOutputError


ResponseT = TypeVar("ResponseT", bound=BaseModel)


@dataclass(frozen=True, slots=True)
class NemotronConfig:
    base_url: str
    model: str
    api_key: str | None = None
    model_version: str | None = None
    provider: str = "modal-vllm"
    timeout_seconds: float = 120.0
    max_retries: int = 2
    temperature: float = 0.0
    max_tokens: int = 4096
    repetition_penalty: float | None = None
    stop: tuple[str, ...] = ()
    response_prefix: str | None = None
    project_name_anchor: str | None = None
    enable_thinking: bool = False
    separate_reasoning: bool | None = None
    log_request_payload: bool = False
    log_raw_response: bool = False
    diagnostic_log_dir: str | None = None


class NemotronClient:
    """Calls vLLM's OpenAI-compatible chat-completions endpoint."""

    def __init__(self, config: NemotronConfig) -> None:
        self.config = config

    def generate(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        response_model: type[ResponseT],
    ) -> ResponseT:
        schema = response_model.model_json_schema()
        self._apply_source_constraints(schema, user_prompt)
        if self.config.project_name_anchor:
            candidate_schema = schema.get("$defs", {}).get("CandidateProject")
            if not isinstance(candidate_schema, dict):
                raise ValueError(
                    "project_name_anchor requires a CandidateProject response schema"
                )
            candidate_schema["properties"]["name"] = {
                "const": self.config.project_name_anchor,
                "type": "string",
            }
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        if self.config.response_prefix:
            messages.append(
                {"role": "assistant", "content": self.config.response_prefix}
            )

        payload = {
            "model": self.config.model,
            "temperature": 0.0,
            "max_tokens": self.config.max_tokens,
            "chat_template_kwargs": {
                "enable_thinking": self.config.enable_thinking,
            },
            "messages": messages,
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": response_model.__name__,
                    "schema": schema,
                    "strict": True,
                },
            },
        }
        if self.config.repetition_penalty is not None:
            payload["repetition_penalty"] = self.config.repetition_penalty
        if self.config.stop:
            payload["stop"] = list(self.config.stop)
        if self.config.response_prefix:
            payload["continue_final_message"] = True
        if self.config.separate_reasoning is not None:
            payload["separate_reasoning"] = self.config.separate_reasoning
        raw = self._post_json(payload)
        try:
            message = raw["choices"][0]["message"]
        except (KeyError, IndexError, TypeError) as exc:
            raise ModelTransportError("model response omitted message content") from exc

        content = message.get("content")
        if content is None and not self.config.enable_thinking:
            content = message.get("reasoning_content")
        if not isinstance(content, (str, list)):
            raise ModelTransportError("model response omitted message content")

        if isinstance(content, list):
            content = "".join(
                item.get("text", "") for item in content if isinstance(item, dict)
            )
        if self.config.log_raw_response:
            self._print_raw("NEMOTRON_RAW_CONTENT", content)
        content = self._restore_response_prefix(content)
        try:
            return response_model.model_validate_json(self._strip_json_fence(content))
        except (ValidationError, ValueError, TypeError) as exc:
            raise StructuredOutputError(f"invalid structured model output: {exc}") from exc

    def _post_json(self, payload: dict) -> dict:
        url = f"{self.config.base_url.rstrip('/')}/chat/completions"
        headers = {"Content-Type": "application/json"}
        if self.config.api_key:
            headers["Authorization"] = f"Bearer {self.config.api_key}"
        request_text = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        request_id = hashlib.sha256(request_text.encode()).hexdigest()[:16]
        if self.config.log_request_payload:
            self._print_raw("NEMOTRON_REQUEST_PAYLOAD", request_text)
        self._save_diagnostic(request_id, "request", request_text)
        body = request_text.encode("utf-8")
        last_error: Exception | None = None

        for attempt in range(self.config.max_retries + 1):
            request = Request(url, data=body, headers=headers, method="POST")
            try:
                with urlopen(request, timeout=self.config.timeout_seconds) as response:
                    response_text = response.read().decode("utf-8")
                    if self.config.log_raw_response:
                        self._print_raw("NEMOTRON_RAW_HTTP_BODY", response_text)
                    self._save_diagnostic(request_id, "response", response_text)
                    return json.loads(response_text)
            except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
                last_error = exc
                if attempt < self.config.max_retries:
                    time.sleep(2**attempt)

        raise ModelTransportError(
            f"Nemotron endpoint failed after {self.config.max_retries + 1} attempts"
        ) from last_error

    @staticmethod
    def _print_raw(label: str, value: str) -> None:
        print(f"--- {label} BEGIN ---", flush=True)
        print(value, flush=True)
        print(f"--- {label} END ---", flush=True)

    def _save_diagnostic(self, request_id: str, kind: str, value: str) -> None:
        if not self.config.diagnostic_log_dir:
            return
        output_dir = Path(self.config.diagnostic_log_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / f"{request_id}-{kind}.json").write_text(
            value,
            encoding="utf-8",
        )

    @staticmethod
    def _strip_json_fence(content: str) -> str:
        value = content.strip()
        if value.startswith("```json") and value.endswith("```"):
            return value[7:-3].strip()
        if value.startswith("```") and value.endswith("```"):
            return value[3:-3].strip()
        return value

    def _restore_response_prefix(self, content: str) -> str:
        prefix = self.config.response_prefix
        if not prefix or content.startswith(prefix):
            return content
        try:
            parsed = json.loads(content)
        except json.JSONDecodeError:
            parsed = None
        if isinstance(parsed, dict):
            return content
        return f"{prefix}{content}"

    @staticmethod
    def _apply_source_constraints(schema: dict, user_prompt: str) -> None:
        candidate_schema = schema.get("$defs", {}).get("CandidateProject")
        evidence_schema = schema.get("$defs", {}).get("FieldEvidence")
        if not isinstance(candidate_schema, dict):
            return

        marker_start = "BEGIN UNTRUSTED SOURCE_ELEMENTS\n"
        marker_end = "\nEND UNTRUSTED SOURCE_ELEMENTS"
        if marker_start not in user_prompt or marker_end not in user_prompt:
            return
        source_json = user_prompt.split(marker_start, 1)[1].split(marker_end, 1)[0]
        try:
            source_elements = json.loads(source_json)
        except json.JSONDecodeError:
            return
        source_texts = [
            element.get("text", "")
            for element in source_elements
            if isinstance(element, dict) and isinstance(element.get("text"), str)
        ]
        source_text = " ".join(source_texts)
        sentences = [
            sentence.strip()
            for text in source_texts
            for sentence in re.split(r"(?<=[.!?])\s+", text)
            if sentence.strip()
        ]
        properties = candidate_schema.get("properties", {})
        if sentences and isinstance(properties.get("description"), dict):
            properties["description"] = {
                "enum": list(dict.fromkeys(sentences)),
                "type": "string",
            }

        allowed_statuses = ["approved", "planned", "proposed"]
        source_statuses = [
            status
            for status in allowed_statuses
            if re.search(rf"\b{re.escape(status)}\b", source_text, re.IGNORECASE)
        ]
        if source_statuses and isinstance(properties.get("status"), dict):
            properties["status"] = {"enum": source_statuses, "type": "string"}

        if isinstance(evidence_schema, dict):
            evidence_properties = evidence_schema.get("properties", {})
            if isinstance(evidence_properties.get("field_name"), dict):
                evidence_properties["field_name"] = {
                    "enum": [
                        "project_name",
                        "project_type",
                        "voltage_kv",
                        "start_date",
                        "end_date",
                        "status",
                        "location_text",
                    ],
                    "type": "string",
                }
