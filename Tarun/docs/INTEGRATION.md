# Extraction integration guide

## Pipeline contract

The pipeline has four explicit boundaries:

1. `extraction.parsing` converts TXT, Markdown, CSV, JSON, PDF, or DOCX input into
   `DocumentChunk` objects. Each chunk retains its source ID, physical location,
   SHA-256 document hash, parser version, element count, and original text. A
   missing source or an empty parse raises an explicit ingestion error before any
   model call.
2. `ExtractorAgent` asks an OpenAI-compatible model for a
   `CandidateProjectBatch`. Candidates may be incomplete but must conform to the
   Pydantic schema.
3. `ValidatorAgent` optionally obtains a second model review, resets source
   metadata to authoritative chunk values, removes quotations absent from the
   source, and checks record-required fields.
4. `ExtractionSwarm` processes chunks concurrently and returns an `ExtractionRun`
   containing both resolved and unresolved validation results plus a diagnostic
   manifest for every model request. Only resolved results contain a
   `ProjectRecord`.

This separation is intentional: consumers should persist `result.record`, never
the candidate, and only when `outcome` is `PASS` or `CORRECTED`.

## Model endpoint configuration

The client uses the OpenAI-compatible `POST /chat/completions` interface with
strict JSON Schema output. Set:

```bash
export NEMOTRON_BASE_URL=https://your-vllm-host/v1
export NEMOTRON_MODEL=your-model-name
export NEMOTRON_API_KEY=optional-token
export NEMOTRON_MODEL_VERSION=optional-deployment-version
export NEMOTRON_PROVIDER=modal-vllm
export NEMOTRON_MAX_TOKENS=4096
export NEMOTRON_ENABLE_THINKING=false
export NEMOTRON_LOG_REQUEST_PAYLOAD=false
export NEMOTRON_LOG_RAW_RESPONSE=false
export NEMOTRON_DIAGNOSTIC_LOG_DIR=.diagnostics/nemotron
export EXTRACTION_MAX_WORKERS=4
export MODEL_VALIDATION=true
```

Structured extraction disables Nemotron reasoning by default and caps each model
response at 4,096 tokens. This prevents hidden reasoning from consuming the model's
full context window before JSON output. Increase `NEMOTRON_MAX_TOKENS` only for
chunks expected to contain many projects; enable thinking only for experiments.

`MODEL_VALIDATION=false` skips the second model call while retaining deterministic
evidence and required-field checks. This is useful for latency experiments, but
the deterministic validator always runs.

Request logging is opt-in because payloads contain source text. When enabled, the
client prints the exact JSON request immediately before inference. Setting
`NEMOTRON_DIAGNOSTIC_LOG_DIR` also saves paired request and response JSON files,
keyed by a request-content hash. Authorization headers and API keys are never
written to these files.

## Grounding and failure behavior

Production prompts contain instructions, the JSON schema, authoritative context,
and the current `SOURCE_ELEMENTS`; they contain no realistic example projects.
Every source element has a stable `source_id`, `element_id`, and source text. The
model-facing schema requires at least one project and therefore must only receive
chunks that an upstream detector has identified as project descriptions.

Each populated project fact must include field-specific evidence referencing the
same element ID. Deterministic validation checks normalized quote containment and
basic field meaning, including distinguishing construction-start evidence from
completion or in-service evidence. Source URL, document hash, and page/row metadata
always come from ingestion rather than model output.

Failures are explicit:

- unreadable source: source retrieval error;
- empty parsed content: parsing error before inference;
- valid content with no projects: upstream detector skips structured extraction;
- invalid or mismatched evidence: unresolved candidate with no record;
- unavailable model or invalid structured output: extraction failure.

There is no sample-record fallback and no extraction-result cache. Manifest fields
currently report `cache_hit=false`; any future cache must key on input content,
model, prompt, and schema versions.

## Modal Nemotron deployment

`modal_nemotron.py` adapts Modal's Nemotron 3 SGLang recipe to this pipeline. It
serves `nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B-NVFP4` on one B200 GPU and scales to
zero after five idle minutes. The endpoint is intentionally unauthenticated for
hackathon integration testing, so do not publish its URL.

Authenticate once, then run the end-to-end structured-output smoke test:

```bash
python -m modal setup
python -m modal run modal_nemotron.py
```

The smoke test waits through the cold start, calls the same extractor and
validator used by the API, prints the exact request and response for inspection,
and fails unless Nemotron emits a validated project record. Its checked-in input is
an isolated synthetic fixture, not a claim that a real utility document was
ingested. Modal returns HTTP 503 while a scale-to-zero container is starting; the
smoke test retries those responses with exponential backoff. The development URL
created by `modal run` expires when the command exits and must not be reused.

To keep the endpoint available after the command exits, deploy it:

```bash
python -m modal deploy modal_nemotron.py
```

A scale-to-zero deployment can still return temporary 503 responses during a
cold start. To eliminate those cold-start responses, keep one B200 replica warm:

```bash
MODAL_MIN_CONTAINERS=1 python -m modal deploy modal_nemotron.py
```

An always-warm replica incurs continuous GPU charges. Leave
`MODAL_MIN_CONTAINERS` unset for lower-cost testing.

Use the deployment URL with `/v1` appended as `NEMOTRON_BASE_URL`, set
`NEMOTRON_MODEL=nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B-NVFP4`, and use a larger
`NEMOTRON_MAX_RETRIES` value when callers must tolerate scale-from-zero cold starts.

## HTTP integration

Run `uvicorn main:app --host 0.0.0.0 --port 8000`, then send one chunk:

```bash
curl -X POST http://localhost:8000/extract/document \
  -H 'content-type: application/json' \
  -d '{
    "source_id": "irp-2026",
    "source_name": "integrated-resource-plan.pdf",
    "utility_id": "utility-a",
    "page_or_row": "page:17",
    "content": "The North Ridge Substation project will add a new 115 kV substation in North Ridge."
  }'
```

The service constructs and caches its swarm on the first request. Missing model
configuration produces HTTP 503; schema errors produce HTTP 422. `/health` does
not call the model and can be used for liveness checks.

The compatibility endpoint `POST /extract` accepts and returns a validated
`CandidateProject`. It performs schema validation only and is useful when another
service owns model inference.

## Batch integration in Python

```python
from agents.factory import create_swarm_from_env
from extraction.parsing import parse_document
from project_intelligence.contracts import SourceAccess

chunks = parse_document(
    "plan.pdf",
    utility_id="utility-a",
    source_id="irp-2026",
    source_access=SourceAccess.PUBLIC,
)
run = create_swarm_from_env().run(chunks)
records = [result.record for result in run.results if result.record is not None]
```

The built-in HTTP client retries transport failures with exponential backoff.
Retrying an entire orchestration run is safe for persistence when records are
upserted by their stable `project_id`.

## Parsing experiments

Compare fixed-width and paragraph-aware chunking without calling a model:

```bash
python -m extraction.experiments.compare_chunking \
  evals/fixtures/sample-plan.txt --utility-id utility-a --chunk-size 500
```

The JSON output reports chunk count, retained character count, size distribution,
and parser time. Paragraph chunking is the default; fixed chunking is useful as a
baseline. PDF and DOCX parsing require the `documents` dependency group.

## Quality evaluation and gold data

The checked-in gold set is `evals/gold/projects.jsonl`. Each line contains a
`case_id`, its source chunk, and the expected projects. It includes a positive
construction project and a policy/forecast hard negative.

Create predictions in the same JSONL shape and run:

```bash
python -m evals.quality evals/gold/projects.jsonl predictions.jsonl
```

The evaluator reports project detection precision, recall, F1, and field accuracy.
Projects match by `source_project_id` when available, otherwise by normalized
project name. Expand the gold set with reviewed production examples, especially
zero-project chunks, ambiguous schedules, tables, and duplicate project mentions.

## Testing and extension points

Run `python -m pytest`. Tests cover parsing, evidence rejection, metadata correction,
orchestration, quality metrics, and API schema behavior. Model tests use an
in-memory structured client and do not require credentials or network access.

Remote extraction accepts only chunks whose `source_access` is explicitly
`PUBLIC`. `UNKNOWN` sources require review, and `CEII` sources are rejected before
the client is called. Local mock extraction remains available for UI development
without a GPU.

To use another model provider, implement the `StructuredClient.generate` protocol
from `agents.extractor`. To add a parser, return `(location, text)` sections from
`extraction.parsing._extract_sections` and add the suffix to `SUPPORTED_SUFFIXES`.
