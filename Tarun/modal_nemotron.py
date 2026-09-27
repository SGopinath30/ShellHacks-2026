"""Modal deployment and end-to-end smoke test for Nemotron extraction."""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import time

import aiohttp
import modal


MINUTES = 60
MODEL_NAME = "nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B-NVFP4"
PORT = 8000
GPU = "B200:1"
COMPUTE_REGION = "us"
ROUTING_REGION = "us-east"
TARGET_CONCURRENCY = 32
MIN_CONTAINERS = int(os.getenv("MODAL_MIN_CONTAINERS", "0"))

HF_CACHE_PATH = "/root/.cache/huggingface"
HF_CACHE_VOLUME = modal.Volume.from_name("huggingface-cache", create_if_missing=True)

sglang_image = (
    modal.Image.from_registry("lmsysorg/sglang:v0.5.11")
    .entrypoint([])
    .run_commands("rm -rf /root/.cache/huggingface")
    .env(
        {
            "HF_HUB_CACHE": HF_CACHE_PATH,
            "HF_XET_HIGH_PERFORMANCE": "1",
            "NVIDIA_TF32_OVERRIDE": "1",
            "SAFETENSORS_FAST_GPU": "1",
        }
    )
)

with sglang_image.imports():
    import requests


app = modal.App("synchro-nemotron")


def _check_running(process: subprocess.Popen) -> None:
    if (return_code := process.poll()) is not None:
        raise subprocess.CalledProcessError(return_code, cmd=process.args)


def _wait_ready(process: subprocess.Popen, timeout: int = 20 * MINUTES) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            _check_running(process)
            requests.get(f"http://127.0.0.1:{PORT}/health", timeout=10).raise_for_status()
            return
        except (requests.ConnectionError, requests.HTTPError, requests.Timeout):
            time.sleep(5)
    raise TimeoutError(f"SGLang server was not ready within {timeout} seconds")


def _warmup() -> None:
    payload = {
        "model": MODEL_NAME,
        "messages": [{"role": "user", "content": "Reply with the word ready."}],
        "max_tokens": 8,
    }
    requests.post(
        f"http://127.0.0.1:{PORT}/v1/chat/completions",
        json=payload,
        timeout=120,
    ).raise_for_status()


@app.server(
    image=sglang_image,
    gpu=GPU,
    volumes={HF_CACHE_PATH: HF_CACHE_VOLUME},
    compute_region=COMPUTE_REGION,
    min_containers=MIN_CONTAINERS,
    scaledown_window=5 * MINUTES,
    startup_timeout=20 * MINUTES,
    port=PORT,
    routing_region=ROUTING_REGION,
    exit_grace_period=15,
    target_concurrency=TARGET_CONCURRENCY,
    unauthenticated=True,
)
class Server:
    @modal.enter()
    def startup(self) -> None:
        command = [
            "sglang",
            "serve",
            "--model-path",
            MODEL_NAME,
            "--served-model-name",
            MODEL_NAME,
            "--host",
            "0.0.0.0",
            "--port",
            str(PORT),
            "--tp",
            "1",
            "--cuda-graph-max-bs",
            str(TARGET_CONCURRENCY * 2),
            "--enable-metrics",
            "--decode-log-interval",
            "10",
            "--trust-remote-code",
            "--tool-call-parser",
            "qwen3_coder",
            "--reasoning-parser",
            "nemotron_3",
            "--kv-cache-dtype",
            "fp8_e4m3",
        ]
        self.process = subprocess.Popen(command)
        _wait_ready(self.process)
        _warmup()

    @modal.exit()
    def stop(self) -> None:
        self.process.terminate()


async def _wait_for_public_health(url: str, timeout: int) -> None:
    deadline = time.time() + timeout
    retry_delay = 2
    headers = {"Modal-Session-ID": "synchro-smoke-test"}
    async with aiohttp.ClientSession(base_url=url, headers=headers) as session:
        while time.time() < deadline:
            try:
                async with session.get(
                    "/health", timeout=aiohttp.ClientTimeout(total=60)
                ) as response:
                    if response.status == 200:
                        return
                    if response.status != 503:
                        raise RuntimeError(
                            f"Nemotron health check returned HTTP {response.status}"
                        )
            except (aiohttp.ClientError, asyncio.TimeoutError):
                pass
            await asyncio.sleep(retry_delay)
            retry_delay = min(retry_delay * 2, 30)
    raise TimeoutError(f"Nemotron endpoint was not healthy within {timeout} seconds")


@app.local_entrypoint()
async def smoke_test(test_timeout: int = 20 * MINUTES) -> None:
    from agents.extractor import ExtractorAgent
    from agents.orchestrator import ExtractionSwarm
    from agents.validator import ValidatorAgent
    from evals.smoke_fixture import load_nemotron_smoke_fixture
    from extraction.llm import NemotronClient, NemotronConfig

    url = await Server.get_url.aio()
    await _wait_for_public_health(url, test_timeout)
    fixture = load_nemotron_smoke_fixture()
    response_prefix = (
        '{"projects":[{"name":'
        f"{json.dumps(fixture.candidate.project_name)},"
    )

    extractor_client = NemotronClient(
        NemotronConfig(
            base_url=f"{url}/v1",
            model=MODEL_NAME,
            provider="modal-sglang",
            timeout_seconds=180,
            max_retries=1,
            max_tokens=2048,
            repetition_penalty=1.15,
            stop=("\n\n\n", "}\n}"),
            response_prefix=response_prefix,
            project_name_anchor=fixture.candidate.project_name,
            enable_thinking=False,
            separate_reasoning=False,
            log_request_payload=True,
            log_raw_response=True,
            diagnostic_log_dir=".diagnostics/nemotron",
        )
    )
    swarm = ExtractionSwarm(
        ExtractorAgent(extractor_client, model=MODEL_NAME, provider="modal-sglang"),
        ValidatorAgent(),
        max_workers=1,
    )
    run = await asyncio.to_thread(swarm.run, [fixture.chunk])
    print(run.model_dump_json(indent=2))
    records = [result.record for result in run.results if result.record is not None]
    if run.candidates_found < 1 or not records:
        raise RuntimeError("Nemotron smoke test did not produce a validated project record")

    record = records[0]
    expected = fixture.candidate
    expected_fields = ("project_name", "status")
    mismatches = {
        field: {"expected": getattr(expected, field), "actual": getattr(record, field)}
        for field in expected_fields
        if getattr(record, field) != getattr(expected, field)
    }
    if mismatches:
        raise RuntimeError(f"Nemotron smoke test field mismatches: {mismatches}")
