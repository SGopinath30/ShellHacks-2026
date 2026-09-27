# Decision Ledger

SYNCHRO's primary user is a Regional / Electric Transmission Planning Manager. A Transmission Construction / Project Manager is a secondary user for execution planning. The manager reviews a cross-utility opportunity, sees the spatial and timing evidence, and records a decision. "Approve coordination" means approve further coordination review; it does not combine ownership or authorize construction of either utility project.

## Opportunity page for Lenovo

Use the `/api/v1` opportunity detail. Show project names, both utilities, distance and method, spatial tier, timing relationship, source evidence, geometry quality, validation state, and fixture flags. Put the actions `Under Review`, `Needs More Data`, `Approve Coordination`, `Propose Coordinated Plan`, and `Dismiss` beside the opportunity. Require a reason for each action. Use `Overview | Evidence | Decision Ledger` tabs. The Decision Ledger tab reads the event history below and shows the newest event first, including actor, timestamp, reason, analysis at decision, project version IDs, and model versions.

Use the server's `decision_context_hash` from the detail response when posting a decision. On a 409, refresh the detail and ask the manager to review the new analysis before resubmitting. Use one `idempotency_key` per user action to avoid duplicate events on network retries.

The current API has **no Impact Engine**. `impact_estimate` and `impact_model_version` are `null`. Do not show sample dollar, day, or acreage figures as calculated results. When an impact model exists, its estimate, source assumptions, and model version must be included in the server-generated snapshot before the UI displays or records them.

## API

`GET /api/v1/opportunities/{pair_id}` returns the opportunity, `impact_estimate: null`, `impact_model_version: null`, and `decision_context_hash`. For profiles or distance overrides, pass the same query parameters to the decision POST.

`POST /api/v1/opportunities/{pair_id}/decisions`:

```json
{
  "action": "APPROVE_COORDINATION",
  "actor_id": "manager-123",
  "actor_role": "Regional Transmission Planning Manager",
  "reason": "Evaluate shared contractor mobilization and staging.",
  "decision_context_hash": "<hash from opportunity detail>",
  "idempotency_key": "<unique ID for this click>"
}
```

Actions are `UNDER_REVIEW`, `NEEDS_MORE_DATA`, `APPROVE_COORDINATION`, `PROPOSE_COORDINATED_PLAN`, and `DISMISS`. The server assigns the timestamp. A changed analysis or project version returns 409. Each successful POST returns the new event with its complete analysis snapshot.

`GET /api/v1/opportunities/{pair_id}/decision-ledger` returns `current_status`, `requires_re_review`, and all events newest first. The history remains available when a pair no longer appears in the current analysis. `UNREVIEWED` is the initial status. The analysis engine appends `OPPORTUNITY_CREATED` on first calculation for a configuration and `OPPORTUNITY_RECOMPUTED` only when its resulting snapshot changes. When a project version used by a past decision is replaced, import appends `PROJECT_VERSION_CHANGED` with the old and new version IDs. These system events do not alter the manager's status. `requires_re_review` becomes true if an analysis or project version changed after the latest manager decision.

`POST /api/v1/opportunities/{pair_id}/audit-pdf` accepts the exporting manager's ID and role, returns a timestamped PDF download, and appends `AUDIT_EXPORTED`. The event retains the canonical audit payload, snapshot SHA-256, exact PDF SHA-256, filename, audit ID, generator, and timestamp. The PDF contains an executive summary, coordinate comparison, geometry warnings, source appendix, reviewer decision, project versions, and the prior append-only trail. The byte hash is returned in `X-SYNCHRO-PDF-SHA256`; it cannot be printed inside the same PDF without creating a circular hash.

`POST /api/v1/opportunities/{pair_id}/decisions/{event_id}/reason` accepts `actor_id`, `actor_role`, `new_reason`, and optional `idempotency_key`. It appends a `REASON_UPDATED` event with `target_event_id`, `old_reason`, and `new_reason`. It preserves the original decision event and its snapshot.

The shared `X-API-Key` protects writes and Decision Ledger reads when `WRITE_API_KEY` is configured. It does **not** authenticate an individual manager: `actor_id` and `actor_role` are currently client assertions. Connect this API to individual sign-in and derive actor identity server-side before presenting the ledger as a verified enterprise audit. Lenovo should call ledger routes through a trusted server proxy; do not put API keys in the browser.

## Record boundaries

The new table is append-only: SQL rejects updates and deletes. It retains the full opportunity data, including both project versions, source evidence, geometry provenance, distance, tier, temporal relationship, engine version, and calculation configuration. Existing legacy `/matches/{id}/review` and `synchro.reviews` are separate mutable paths; Lenovo should use the `/api/v1` ledger.

Material events still requiring implementation are impact assumption changes and estimate recalculation, plus explicit human field corrections with a verified actor. Those require hooks in their respective services and should append events using the same immutable model when built. Hovers, map pans, and page views do not belong in the ledger. Alerts are outside this workflow.

Run `python -m scripts.init_challenge_db` against the configured PostGIS database to install the ledger table and its append-only trigger.
