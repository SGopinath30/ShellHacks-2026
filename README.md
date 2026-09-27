# Synchro extraction backend

Synchro turns fragmented utility construction plans into an explainable
geospatial timeline, using AI-assisted document extraction and deterministic
spatial and schedule matching to surface cross-utility coordination opportunities.

This repository contains the project-intelligence trust layer. Structured starter
data is parsed deterministically; messy source text can use Nemotron as an
extraction accelerator. Canonical candidates retain field-level evidence,
schedule semantics, source access classification, geometry-association results,
and immutable version history before anything is marked ready for ASUS.

## Quick start

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e '.[dev,documents,spreadsheets,modal]'
python -m pytest
uvicorn main:app --reload
```

Parse an explicitly public starter workbook without invoking AI:

```bash
synchro-project-intelligence starter.xlsx \
  --source-version-id SV-STARTER-2026 \
  --utility DESC \
  --source-access PUBLIC \
  --output candidates.json
```

The output includes the source SHA-256, canonical candidates, field evidence, and
deterministic validation results. See
[docs/PROJECT_INTELLIGENCE.md](docs/PROJECT_INTELLIGENCE.md) for the trust-layer
contracts and Dell/ASUS handoff.

With the Dell package and official public filings present locally, run Phase B/C:

```bash
python -m project_intelligence.phase_bc \
  data/live/handoff/PKG-b8fa62d495ff092c9e54e9f4 \
  --phase-a data/derived/canonical_candidate_projects.json \
  --current-sources data/live/current_sources \
  --output-dir data/derived
```

This path is deterministic and local. It does not invoke Modal or Nemotron.

`POST /extract` validates a `CandidateProject` payload. `POST /extract/document`
runs the complete agent pipeline and requires `NEMOTRON_BASE_URL` and
`NEMOTRON_MODEL`. OpenAPI documentation is available at `/docs` while the server
is running.

See [docs/INTEGRATION.md](docs/INTEGRATION.md) for configuration, payloads,
quality evaluation, and extension points.

Run the GPU-backed Nemotron smoke test with
`python -m modal run modal_nemotron.py`. Deploy the scale-to-zero endpoint with
`python -m modal deploy modal_nemotron.py`. A `modal run` URL is temporary and
expires as soon as the command exits. The smoke test uses synthetic eval data;
real extraction requires downloading and parsing a specific source document first.

Frontend routes are available under `/api`:

- `GET /api/projects` returns validated records stored by the current API process.
- `POST /api/extract` accepts `{"text":"..."}`, runs extraction plus deterministic
  validation, persists the validated record, and returns its source evidence.

`/api/extract` uses an instant source-aware local mock by default. Set
`USE_MODAL_INFERENCE=true` or pass `?use_modal_inference=true` only when a configured
remote Nemotron endpoint should be called. The default path never starts Modal GPU
workloads. Remote requests must also set `"source_access":"PUBLIC"`;
unclassified and CEII inputs are rejected before the model call.
