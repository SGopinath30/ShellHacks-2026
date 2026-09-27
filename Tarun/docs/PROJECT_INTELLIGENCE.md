# Project intelligence trust layer

`project_intelligence` is the authoritative contract and validation package for
the Mac role. The older `extraction.models` types remain the model-facing API;
`project_intelligence.extraction.to_canonical_candidate` is the explicit bridge
from model output into the shared canonical contract.

## Pipeline

```text
Dell SourceArtifact / GeometryCandidate
                 │
                 ▼
deterministic parser or constrained model adapter
                 │
                 ▼
CandidateProject + FieldEvidence[]
                 │
                 ▼
schedule, evidence, geometry, and identity validation
                 │
                 ▼
ProjectValidationResult
                 │
                 ▼
AcceptedProjectVersion for ASUS
```

The model never decides distance, overlap, coordination tiers, or ranking.

## Deterministic ingestion

XLSX, CSV, and JSON project rows bypass Nemotron:

```bash
synchro-project-intelligence starter.xlsx \
  --source-version-id SV-STARTER-2026 \
  --utility DESC \
  --source-access PUBLIC \
  --source-url https://example.test/public-plan \
  --output candidates.json
```

The parser:

- computes and reports the source SHA-256;
- creates stable candidate and evidence IDs;
- retains workbook sheet, row, and column locators;
- classifies in-service and need dates as milestones, not construction windows;
- preserves quarter, month, season, and year precision as bounded ranges;
- leaves unsupported normalized values null and linked to unresolved evidence;
- never invokes an LLM.

### Dell handoff conversion

Convert Dell's portable `mac_handoff.json` package into canonical Mac records:

```bash
python -m project_intelligence.extraction.dell_handoff \
  data/live/handoff/PKG-b8fa62d495ff092c9e54e9f4 \
  --output data/derived/canonical_candidate_projects.json
```

Conversion verifies every preserved raw-file SHA-256 before reading project
seeds. Organizer IDs remain `starter_project_id` values rather than being
misrepresented as utility-issued IDs. Multiple voltages in one starter row remain
unresolved in the scalar canonical field, with the complete voltage list retained
in field evidence. `PUBLIC_ASSUMED` sources map to `UNKNOWN` access and therefore
remain `NEEDS_REVIEW` until public access is confirmed.

### Phase B/C verification

After preserving the current public utility filings under
`data/live/current_sources`, run deterministic source reconciliation and geometry
review:

```bash
python -m project_intelligence.phase_bc \
  data/live/handoff/PKG-b8fa62d495ff092c9e54e9f4 \
  --phase-a data/derived/canonical_candidate_projects.json \
  --current-sources data/live/current_sources \
  --output-dir data/derived
```

Phase B parses the latest registered DESC planning documents and the Georgia
Power 2025 IRP public-disclosure filing locally. The Georgia Power PDF must match
the copy inside the official Georgia PSC ZIP byte-for-byte. New facts produce new
candidate records and comparisons; starter records are never overwritten.

Phase C converts Dell's OSM records into canonical geometry candidates and checks
utility, voltage, feature identity, and endpoint association. A line matching
only one endpoint cannot be accepted as the project route. Approximate starter
segments also remain review-only. The outputs are
`phase_b_source_verification.json` and `phase_c_geometry_validation.json`.

## Verification rules

Canonical states are `UNVERIFIED`, `VERIFIED_RULE`, `VERIFIED_HUMAN`,
`UNRESOLVED`, and `REJECTED`. Model confidence is not a verification state.

`validate_candidate` rejects failed evidence associations and impossible
schedules. It returns `NEEDS_REVIEW` for unclassified sources, ambiguous evidence,
partially feasible schedules, or geometry that has not passed association rules.
Only an `ACCEPTED` result has `ready_for_asus=true` and can be passed to
`accept_candidate_version`.

Each populated canonical field references `FieldEvidence`. Evidence includes the
source version, physical locator, original source text, normalized value,
extraction method, field state, and project/attribute association state.

## Source safety

Only explicitly `PUBLIC` source chunks may reach remote inference. `CEII` and
`UNKNOWN` chunks stop before the network client is called. A source marked
`UNKNOWN` may still be parsed locally, but its validation result requires review.

## Geometry and identity

Dell supplies geometry candidates. Use `attach_validated_geometry` to preserve the
provider/origin and evaluate utility, voltage, jurisdiction, and endpoint/name
signals. A conflict rejects the association; a name match by itself requires
review.

`reconcile_projects` auto-approves identity only when authoritative external IDs
match. Name-only matches produce a review proposal and never merge records.
`compare_versions` reports `UNCHANGED`, `UPDATED`, or `UNRESOLVED`, while
`accept_candidate_version` creates a linked immutable version instead of
overwriting the previous source value.

## ASUS fixture

`evals/fixtures/accepted_project_version.json` is a synthetic development fixture
that validates against `AcceptedProjectVersion`. It is explicitly marked
`STARTER_DATA`; it is not represented as current utility-verified data.

All ten starter projects now have source-derived Phase B candidates. Identity
reconciliation remains review-gated when the starter workbook lacks an
authoritative utility project ID. Phase C accepts only independently supported
endpoint geometry; review and rejected alternatives remain in the report rather
than being silently discarded. Public source bytes and generated reports remain
gitignored local artifacts.
