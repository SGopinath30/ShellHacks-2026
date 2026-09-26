# Synchro extraction backend

Synchro turns fragmented utility construction plans into an explainable
geospatial timeline, using AI-assisted document extraction and deterministic
spatial and schedule matching to surface cross-utility coordination opportunities.

This repository currently contains the evidence-grounded extraction backend. It
parses source documents into traceable chunks, runs a structured-output extractor,
validates every candidate against verbatim source evidence, and emits trusted
`ProjectRecord` objects only for resolved candidates. Every run also emits an
input manifest containing source hashes, selected element IDs, parser/model/prompt
versions, and explicit cache/mock flags.

## Quick start

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e '.[dev,documents,modal]'
pytest
uvicorn main:app --reload
```

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
