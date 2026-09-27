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
CREATE TABLE IF NOT EXISTS synchro.ingestion_jobs (
    job_id text PRIMARY KEY,
    status text NOT NULL,
    metadata jsonb NOT NULL DEFAULT '{}',
    created_at timestamptz NOT NULL DEFAULT now()
);
