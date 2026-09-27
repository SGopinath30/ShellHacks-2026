CREATE EXTENSION IF NOT EXISTS postgis;
CREATE SCHEMA IF NOT EXISTS synchro;
CREATE TABLE IF NOT EXISTS synchro.utilities (utility_id text PRIMARY KEY);
CREATE TABLE IF NOT EXISTS synchro.projects (
    project_id text PRIMARY KEY,
    utility_id text NOT NULL REFERENCES synchro.utilities
);
CREATE TABLE IF NOT EXISTS synchro.project_versions (
    version_id text PRIMARY KEY,
    project_id text NOT NULL REFERENCES synchro.projects,
    version_number integer NOT NULL,
    payload jsonb NOT NULL,
    geometry geometry(Geometry, 4326),
    is_current boolean NOT NULL DEFAULT true,
    accepted_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE(project_id, version_number)
);
CREATE UNIQUE INDEX IF NOT EXISTS one_current_version ON synchro.project_versions(project_id) WHERE is_current;
CREATE INDEX IF NOT EXISTS version_geometry ON synchro.project_versions USING gist(geometry);
CREATE INDEX IF NOT EXISTS version_geography ON synchro.project_versions USING gist((geometry::geography)) WHERE is_current;
CREATE TABLE IF NOT EXISTS synchro.project_pairs (
    pair_id text PRIMARY KEY,
    project_low_id text NOT NULL REFERENCES synchro.projects,
    project_high_id text NOT NULL REFERENCES synchro.projects,
    UNIQUE(project_low_id, project_high_id),
    CHECK(project_low_id COLLATE "C" < project_high_id COLLATE "C")
);
CREATE TABLE IF NOT EXISTS synchro.reviews (
    pair_id text PRIMARY KEY REFERENCES synchro.project_pairs,
    status text NOT NULL CHECK(status IN ('unreviewed', 'investigate', 'dismiss', 'contact_utility')),
    note text,
    updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS synchro.decision_ledger (
    event_id uuid PRIMARY KEY,
    pair_id text NOT NULL REFERENCES synchro.project_pairs,
    event_type text NOT NULL CHECK (event_type IN (
        'UNDER_REVIEW', 'NEEDS_MORE_DATA', 'APPROVE_COORDINATION',
        'PROPOSE_COORDINATED_PLAN', 'DISMISS', 'REASON_UPDATED',
        'OPPORTUNITY_CREATED', 'OPPORTUNITY_RECOMPUTED', 'PROJECT_VERSION_CHANGED',
        'AUDIT_EXPORTED'
    )),
    actor_id text NOT NULL,
    actor_role text NOT NULL,
    reason text,
    occurred_at timestamptz NOT NULL DEFAULT now(),
    snapshot jsonb NOT NULL,
    context_hash text NOT NULL,
    details jsonb NOT NULL DEFAULT '{}'::jsonb,
    idempotency_key text,
    UNIQUE (pair_id, idempotency_key)
);
ALTER TABLE synchro.decision_ledger DROP CONSTRAINT IF EXISTS decision_ledger_event_type_check;
ALTER TABLE synchro.decision_ledger ADD CONSTRAINT decision_ledger_event_type_check CHECK (event_type IN (
    'UNDER_REVIEW', 'NEEDS_MORE_DATA', 'APPROVE_COORDINATION',
    'PROPOSE_COORDINATED_PLAN', 'DISMISS', 'REASON_UPDATED',
    'OPPORTUNITY_CREATED', 'OPPORTUNITY_RECOMPUTED', 'PROJECT_VERSION_CHANGED',
    'AUDIT_EXPORTED'
));
CREATE INDEX IF NOT EXISTS decision_ledger_pair_time
    ON synchro.decision_ledger (pair_id, occurred_at DESC, event_id DESC);
CREATE OR REPLACE FUNCTION synchro.prevent_decision_ledger_mutation()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'Audit records are append-only';
END;
$$;
DROP TRIGGER IF EXISTS decision_ledger_append_only ON synchro.decision_ledger;
CREATE TRIGGER decision_ledger_append_only
    BEFORE UPDATE OR DELETE ON synchro.decision_ledger
    FOR EACH ROW EXECUTE FUNCTION synchro.prevent_decision_ledger_mutation();
CREATE TABLE IF NOT EXISTS synchro.opportunity_analysis_state (
    pair_id text NOT NULL REFERENCES synchro.project_pairs,
    configuration_hash text NOT NULL,
    context_hash text NOT NULL,
    PRIMARY KEY (pair_id, configuration_hash)
);
CREATE TABLE IF NOT EXISTS synchro.location_verifications (
    verification_id uuid PRIMARY KEY,
    project_id text NOT NULL REFERENCES synchro.projects,
    from_version_id text NOT NULL REFERENCES synchro.project_versions,
    to_version_id text NOT NULL REFERENCES synchro.project_versions,
    actor_id text NOT NULL,
    actor_role text NOT NULL,
    reason text NOT NULL,
    evidence jsonb NOT NULL,
    occurred_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (project_id, to_version_id)
);
CREATE INDEX IF NOT EXISTS location_verifications_project_time
    ON synchro.location_verifications (project_id, occurred_at DESC);
DROP TRIGGER IF EXISTS location_verifications_append_only ON synchro.location_verifications;
CREATE TRIGGER location_verifications_append_only
    BEFORE UPDATE OR DELETE ON synchro.location_verifications
    FOR EACH ROW EXECUTE FUNCTION synchro.prevent_decision_ledger_mutation();
CREATE TABLE IF NOT EXISTS synchro.ingestion_jobs (
    job_id text PRIMARY KEY,
    status text NOT NULL,
    metadata jsonb NOT NULL DEFAULT '{}',
    created_at timestamptz NOT NULL DEFAULT now()
);

-- Research never writes project versions; a separate human approval transaction does.
CREATE TABLE IF NOT EXISTS synchro.research_proposals (
    proposal_id uuid PRIMARY KEY,
    project_id text NOT NULL REFERENCES synchro.projects,
    base_version_id text NOT NULL REFERENCES synchro.project_versions,
    state text NOT NULL CHECK (state IN ('RUNNING','REVIEW','FAILED','REJECTED','APPLIED')),
    revision integer NOT NULL DEFAULT 1,
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    research jsonb NOT NULL DEFAULT '{}'::jsonb,
    error text,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS research_project_created ON synchro.research_proposals(project_id,created_at DESC);
CREATE UNIQUE INDEX IF NOT EXISTS research_one_running ON synchro.research_proposals(project_id) WHERE state='RUNNING';
CREATE TABLE IF NOT EXISTS synchro.research_reviews (
    review_id uuid PRIMARY KEY,
    proposal_id uuid NOT NULL REFERENCES synchro.research_proposals,
    action text NOT NULL,
    actor_id text NOT NULL,
    reason text NOT NULL,
    proposal_hash text NOT NULL,
    payload jsonb NOT NULL,
    occurred_at timestamptz NOT NULL DEFAULT now()
);
DROP TRIGGER IF EXISTS research_reviews_append_only ON synchro.research_reviews;
CREATE TRIGGER research_reviews_append_only BEFORE UPDATE OR DELETE ON synchro.research_reviews
    FOR EACH ROW EXECUTE FUNCTION synchro.prevent_decision_ledger_mutation();
