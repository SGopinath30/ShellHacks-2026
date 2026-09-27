"""Immutable manager decisions with the opportunity context seen at the time."""
import hashlib
import json
from enum import Enum
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, field_validator
from psycopg.types.json import Jsonb

from . import repository


class Decision(str, Enum):
    UNDER_REVIEW = "UNDER_REVIEW"
    NEEDS_MORE_DATA = "NEEDS_MORE_DATA"
    APPROVE_COORDINATION = "APPROVE_COORDINATION"
    PROPOSE_COORDINATED_PLAN = "PROPOSE_COORDINATED_PLAN"
    DISMISS = "DISMISS"


class DecisionRequest(BaseModel):
    action: Decision
    actor_id: str = Field(min_length=1, max_length=200)
    actor_role: str = Field(min_length=1, max_length=200)
    reason: str = Field(min_length=1, max_length=4000)
    decision_context_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    idempotency_key: str | None = Field(default=None, min_length=1, max_length=200)

    @field_validator("actor_id", "actor_role", "reason")
    @classmethod
    def nonblank(cls, value):
        if not value.strip():
            raise ValueError("Must contain visible text")
        return value.strip()


class ReasonUpdateRequest(BaseModel):
    actor_id: str = Field(min_length=1, max_length=200)
    actor_role: str = Field(min_length=1, max_length=200)
    new_reason: str = Field(min_length=1, max_length=4000)
    idempotency_key: str | None = Field(default=None, min_length=1, max_length=200)

    @field_validator("actor_id", "actor_role", "new_reason")
    @classmethod
    def nonblank(cls, value):
        if not value.strip():
            raise ValueError("Must contain visible text")
        return value.strip()


def snapshot(opportunity):
    # The impact engine is not implemented. Null is intentional: the client
    # cannot inject an unverified cost, time, or ROW estimate into the ledger.
    return {**opportunity, "impact_estimate": None, "impact_model_version": None}


def context_hash(context):
    raw = json.dumps(context, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                     allow_nan=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def record_analysis(conn, opportunity):
    """Append one system event when a given configuration's analysis changes."""
    context = snapshot(opportunity)
    digest = context_hash(context)
    config_digest = context_hash(opportunity["calculation_configuration"])
    pair_id = opportunity["pair_id"]
    conn.execute("SELECT pair_id FROM synchro.project_pairs WHERE pair_id=%s FOR UPDATE", (pair_id,))
    prior = conn.execute("""SELECT context_hash FROM synchro.opportunity_analysis_state
                          WHERE pair_id=%s AND configuration_hash=%s""",
                         (pair_id, config_digest)).fetchone()
    if prior and prior["context_hash"] == digest:
        return
    if prior:
        conn.execute("""UPDATE synchro.opportunity_analysis_state SET context_hash=%s
                      WHERE pair_id=%s AND configuration_hash=%s""",
                     (digest, pair_id, config_digest))
    else:
        conn.execute("""INSERT INTO synchro.opportunity_analysis_state VALUES (%s,%s,%s)""",
                     (pair_id, config_digest, digest))
    event_type = "OPPORTUNITY_RECOMPUTED" if prior else "OPPORTUNITY_CREATED"
    details = {"configuration_hash": config_digest,
               "previous_context_hash": prior["context_hash"] if prior else None}
    conn.execute("""INSERT INTO synchro.decision_ledger
        (event_id,pair_id,event_type,actor_id,actor_role,snapshot,context_hash,details)
        VALUES (%s,%s,%s,'system','Analysis Engine',%s,%s,%s)""",
        (uuid4(), pair_id, event_type, Jsonb(context), digest, Jsonb(details)))


def record_project_version_change(conn, project_id, old_version_id, new_version_id):
    """Flag prior manager decisions whose source project version was replaced."""
    rows = conn.execute("""SELECT DISTINCT ON (pair_id) pair_id,snapshot,context_hash
                         FROM synchro.decision_ledger
                         WHERE event_type IN ('UNDER_REVIEW','NEEDS_MORE_DATA',
                           'APPROVE_COORDINATION','PROPOSE_COORDINATED_PLAN','DISMISS')
                           AND snapshot->'projects' @> %s::jsonb
                         ORDER BY pair_id,occurred_at DESC,event_id DESC""",
                        (Jsonb([{"project_id": project_id, "version_id": old_version_id}]),)).fetchall()
    for row in rows:
        conn.execute("""INSERT INTO synchro.decision_ledger
            (event_id,pair_id,event_type,actor_id,actor_role,snapshot,context_hash,details)
            VALUES (%s,%s,'PROJECT_VERSION_CHANGED','system','Project Import',%s,%s,%s)""",
            (uuid4(), row["pair_id"], Jsonb(row["snapshot"]), row["context_hash"],
             Jsonb({"project_id": project_id, "old_version_id": old_version_id,
                    "new_version_id": new_version_id})))


def response_row(row):
    return {**row, "event_id": str(row["event_id"]),
            "occurred_at": row["occurred_at"].isoformat()}


def status_from_events(events):
    decision_index = next((i for i, event in enumerate(events)
                           if event["event_type"] in Decision._value2member_map_), None)
    current = events[decision_index]["event_type"] if decision_index is not None else "UNREVIEWED"
    newer = events[:decision_index] if decision_index is not None else []
    stale = any(event["event_type"] in {"OPPORTUNITY_RECOMPUTED", "PROJECT_VERSION_CHANGED"}
                for event in newer)
    return current, stale


def ledger(pair_id):
    with repository.connect() as conn:
        pair = conn.execute("SELECT 1 FROM synchro.project_pairs WHERE pair_id=%s", (pair_id,)).fetchone()
        if not pair:
            return None
        rows = conn.execute("""SELECT event_id,pair_id,event_type,actor_id,actor_role,reason,
                           occurred_at,snapshot,context_hash,details
                           FROM synchro.decision_ledger WHERE pair_id=%s
                           ORDER BY occurred_at DESC,event_id DESC""", (pair_id,)).fetchall()
    events = [response_row(row) for row in rows]
    current, stale = status_from_events(events)
    return {"pair_id": pair_id, "current_status": current,
            "requires_re_review": stale, "events": events}


def _lock_and_check(conn, pair_id, context):
    pair = conn.execute("SELECT 1 FROM synchro.project_pairs WHERE pair_id=%s FOR UPDATE", (pair_id,)).fetchone()
    if not pair:
        raise LookupError("Opportunity pair is unknown")
    project_ids = sorted((context["project_a"], context["project_b"]))
    conn.execute("SELECT project_id FROM synchro.projects WHERE project_id=ANY(%s) ORDER BY project_id FOR SHARE",
                 (project_ids,)).fetchall()
    current = conn.execute("""SELECT project_id,version_id FROM synchro.project_versions
                           WHERE project_id=ANY(%s) AND is_current""", (project_ids,)).fetchall()
    versions = {row["project_id"]: row["version_id"] for row in current}
    expected = {p["project_id"]: p["version_id"] for p in context["projects"]}
    if versions != expected:
        raise ValueError("Project versions changed; refresh the opportunity before deciding")


def _existing(conn, pair_id, key, expected):
    if key is None:
        return None
    row = conn.execute("""SELECT event_id,pair_id,event_type,actor_id,actor_role,reason,
                      occurred_at,snapshot,context_hash,details
                      FROM synchro.decision_ledger WHERE pair_id=%s AND idempotency_key=%s""",
                       (pair_id, key)).fetchone()
    if row and any(row[field] != value for field, value in expected.items()):
        raise ValueError("Idempotency key already used for a different event")
    return response_row(row) if row else None


def append_decision(pair_id, opportunity, request):
    context = snapshot(opportunity)
    digest = context_hash(context)
    if request.decision_context_hash != digest:
        raise ValueError("Opportunity analysis changed; refresh before deciding")
    event = {"event_type": request.action.value, "actor_id": request.actor_id,
             "actor_role": request.actor_role, "reason": request.reason,
             "context_hash": digest}
    with repository.connect() as conn:
        _lock_and_check(conn, pair_id, context)
        previous = _existing(conn, pair_id, request.idempotency_key, event)
        if previous:
            return previous
        row = conn.execute("""INSERT INTO synchro.decision_ledger
            (event_id,pair_id,event_type,actor_id,actor_role,reason,snapshot,context_hash,idempotency_key)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
            RETURNING event_id,pair_id,event_type,actor_id,actor_role,reason,
                      occurred_at,snapshot,context_hash,details""",
            (uuid4(), pair_id, request.action.value, request.actor_id, request.actor_role,
             request.reason, Jsonb(context), digest, request.idempotency_key)).fetchone()
    return response_row(row)


def update_reason(pair_id, event_id: UUID, request):
    with repository.connect() as conn:
        pair = conn.execute("SELECT 1 FROM synchro.project_pairs WHERE pair_id=%s FOR UPDATE", (pair_id,)).fetchone()
        if not pair:
            raise LookupError("Opportunity pair is unknown")
        original = conn.execute("""SELECT event_id,reason,snapshot,context_hash FROM synchro.decision_ledger
                              WHERE pair_id=%s AND event_id=%s AND event_type <> 'REASON_UPDATED'""",
                                (pair_id, event_id)).fetchone()
        if not original:
            raise LookupError("Decision event is unknown")
        if request.idempotency_key:
            replay = _existing(conn, pair_id, request.idempotency_key, {
                "event_type": "REASON_UPDATED", "actor_id": request.actor_id,
                "actor_role": request.actor_role, "reason": request.new_reason,
                "context_hash": original["context_hash"]})
            if replay:
                if replay["details"].get("target_event_id") != str(event_id):
                    raise ValueError("Idempotency key already used for a different event")
                return replay
        latest = conn.execute("""SELECT details->>'new_reason' AS reason FROM synchro.decision_ledger
                            WHERE pair_id=%s AND event_type='REASON_UPDATED'
                              AND details->>'target_event_id'=%s
                            ORDER BY occurred_at DESC,event_id DESC LIMIT 1""",
                              (pair_id, str(event_id))).fetchone()
        old_reason = latest["reason"] if latest else original["reason"]
        details = {"target_event_id": str(event_id), "old_reason": old_reason,
                   "new_reason": request.new_reason}
        if old_reason == request.new_reason:
            raise ValueError("Reason is unchanged")
        row = conn.execute("""INSERT INTO synchro.decision_ledger
            (event_id,pair_id,event_type,actor_id,actor_role,reason,snapshot,context_hash,details,idempotency_key)
            VALUES (%s,%s,'REASON_UPDATED',%s,%s,%s,%s,%s,%s,%s)
            RETURNING event_id,pair_id,event_type,actor_id,actor_role,reason,
                      occurred_at,snapshot,context_hash,details""",
            (uuid4(), pair_id, request.actor_id, request.actor_role, request.new_reason,
             Jsonb(original["snapshot"]), original["context_hash"], Jsonb(details),
             request.idempotency_key)).fetchone()
    return response_row(row)
