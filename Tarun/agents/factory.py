"""Environment-driven construction of the production extraction swarm."""

from __future__ import annotations

import os

from agents.extractor import ExtractorAgent
from agents.orchestrator import ExtractionSwarm
from agents.validator import ValidatorAgent
from extraction.llm import NemotronClient, NemotronConfig


def create_swarm_from_env() -> ExtractionSwarm:
    base_url = _required("NEMOTRON_BASE_URL")
    model = _required("NEMOTRON_MODEL")
    provider = os.getenv("NEMOTRON_PROVIDER", "modal-vllm")
    client = NemotronClient(
        NemotronConfig(
            base_url=base_url,
            model=model,
            api_key=os.getenv("NEMOTRON_API_KEY"),
            model_version=os.getenv("NEMOTRON_MODEL_VERSION"),
            provider=provider,
            timeout_seconds=float(os.getenv("NEMOTRON_TIMEOUT_SECONDS", "120")),
            max_retries=int(os.getenv("NEMOTRON_MAX_RETRIES", "2")),
            max_tokens=int(os.getenv("NEMOTRON_MAX_TOKENS", "4096")),
            enable_thinking=os.getenv("NEMOTRON_ENABLE_THINKING", "false").casefold()
            in {"1", "true", "yes"},
            log_request_payload=os.getenv(
                "NEMOTRON_LOG_REQUEST_PAYLOAD", "false"
            ).casefold()
            in {"1", "true", "yes"},
            log_raw_response=os.getenv("NEMOTRON_LOG_RAW_RESPONSE", "false").casefold()
            in {"1", "true", "yes"},
            diagnostic_log_dir=os.getenv("NEMOTRON_DIAGNOSTIC_LOG_DIR"),
        )
    )
    extractor = ExtractorAgent(
        client,
        model=model,
        model_version=os.getenv("NEMOTRON_MODEL_VERSION"),
        provider=provider,
        mock_mode=False,
    )
    use_model_validator = os.getenv("MODEL_VALIDATION", "false").casefold() in {
        "1",
        "true",
        "yes",
    }
    return ExtractionSwarm(
        extractor,
        ValidatorAgent(client if use_model_validator else None),
        max_workers=int(os.getenv("EXTRACTION_MAX_WORKERS", "4")),
    )


def _required(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"{name} must be set")
    return value
