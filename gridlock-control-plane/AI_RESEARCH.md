# Gemini research with human review

The React Location Workbench (`synchro-web`) has **Research with Gemini**, saved
research history, sources, missing evidence, an unverified geometry preview,
outreach drafts, proposal editing, rejection, and **Approve and apply**.
The standalone backend HTML workbench remains a read-only viewer.

## Setup

Configure these variables on the backend only:

- `GEMINI_API_KEY`: a Gemini API key with Google Search grounding access.
- `GEMINI_RESEARCH_MODEL`: defaults to `gemini-2.5-flash`. Choose an available model
  supporting Google Search, URL context, and JSON-schema structured output.
- `WRITE_API_KEY`: required for every research/history/edit/approval endpoint,
  even when ordinary local write routes are open.
- `DATABASE_URL`: the existing PostGIS database.

Run the existing pre-deploy command, `python -m scripts.init_challenge_db`, before
starting the updated API. It adds research proposal and append-only review tables.
Build and serve the updated React frontend. Enter the reviewer key through
**Reviewer access**; Gemini credentials never go in frontend environment variables.

No new Python dependencies are required. Research uses the existing `httpx` client
and the Gemini REST API. Provider configuration and live model access must be
validated with a real API key; tests use simulated provider responses.

## Workflow

1. Select a source-backed project, then start research. The API returns 202 and
   persists a RUNNING proposal tied to the current project version.
2. A fixed-host, read-only SAGIS adapter attempts to retrieve up to five Georgia
   Power owner-matched parcel features for Big Ogeechee. It requests EPSG:4326
   geometry and stores the exact query URL. Results are discovery candidates,
   not confirmed project sites; the envelope and record cap are not exhaustive.
   Other projects use grounded discovery until county-specific adapters exist.
   Unavailable GIS or changed schemas produce an explicit UNAVAILABLE result.
3. Gemini makes one grounded research call, then one structured extraction call.
   The original report, grounding metadata, retrieval date, model, GIS response,
   proposed verification and missing-evidence list are saved. Missing geometry
   produces a null verification rather than invented coordinates.
4. Review the source documents, parcel identity, coordinate derivation, geometry
   quality and current status. Forecast completion dates do not establish actual
   commissioning. Source ownership alone does not establish project identity.
5. If necessary, edit the evidence proposal and save a revision. Reviewer ID and
   reason are recorded with before/after proposal snapshots. Missing evidence
   must be resolved before approval. Outreach is a draft for manual sending;
   the application sends no messages or forms.
6. Confirm the evidence and approve. The server checks the saved proposal hash,
   state and project base version, then atomically saves the verified project,
   location audit, proposal approval audit and APPLIED state. A stale proposal or
   project returns 409. A repeated approval cannot create another version.
7. The React frontend refreshes the project and opportunity data. `completed` and
   `operational` statuses are recordable but excluded by the existing eligibility
   rules. Real source-backed distance must still be strictly under 40 km.

## Boundaries and operation

- The provider has no reviewer credentials, database access or write tools.
  It can only return untrusted evidence proposals. Human approval is a separate
  authenticated endpoint, not a model-controlled function.
- Reviewer access uses the existing shared key; actor IDs are client asserted.
  This does not establish individual identity or independent two-person approval.
- Research allows one running request per project and five starts per project
  per hour. Each provider call has a 60-second HTTP timeout and a 6,000-token
  output cap. GIS uses two requests with 10-second timeouts. The prompt requests
  at most five searches; provider-internal query counts are not a hard server-side
  budget. Configure provider quotas/budgets for spend control.
- Jobs use FastAPI background tasks, not a separate durable worker. Proposal
  records survive restarts; execution does not. RUNNING jobs older than ten
  minutes become FAILED on the next history/start request and can be restarted
  manually. There are no automatic retries or duplicate paid calls.
- No arbitrary source URL is fetched by the backend GIS adapter. Google retrieves
  search/URL-context sources. Grounding is provenance, not proof of correctness.
- The current verification contract supports points and lines, not parcel polygons.
  A reviewer must justify any selected site point; parcel centroids are not
  automatically promoted to verified coordinates.

## API

All routes use `X-API-Key`:

- `POST /api/v1/projects/{project_id}/research`
- `GET /api/v1/projects/{project_id}/research` (latest 20 saved jobs)
- `PUT /api/v1/research/{proposal_id}` with `proposal_hash`, `actor_id`, `reason`, `proposal`
- `POST /api/v1/research/{proposal_id}/review` with `proposal_hash`, `actor_id`,
  `reason`, `action` (`APPROVE` or `REJECT`), `evidence_confirmed`

See `/docs` for typed request schemas. Proposal payloads are validated server-side.
Research failure messages omit raw provider errors to avoid leaking credentials.

## Verification

`python -m pytest tests/test_research.py` covers authentication, approval gates,
stale proposals, reviewer attribution, edits, rejected proposals, provider
boundaries, unavailable GIS and completed-project exclusion.

The opt-in PostGIS integration test requires `RESEARCH_TEST_DATABASE=1` and a
`DATABASE_URL` pointing to an isolated test database. It exercises migration
idempotency, research without project mutation, atomic approval, repeat rejection,
stale-project rollback and append-only audit enforcement. Never enable it against
production. Frontend checks: `npm run build` and `npm run check:render`.

Provider documentation:
https://ai.google.dev/gemini-api/docs/generate-content/google-search
https://ai.google.dev/gemini-api/docs/structured-output
