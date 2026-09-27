CREATE EXTENSION IF NOT EXISTS postgis;

CREATE TABLE IF NOT EXISTS projects (
    project_id              TEXT PRIMARY KEY,
    utility_id              TEXT NOT NULL,
    project_name            TEXT NOT NULL,
    project_type            TEXT NOT NULL,
    voltage_kv              DOUBLE PRECISION,
    start_date               DATE,
    end_date                 DATE,
    start_date_precision     TEXT DEFAULT 'unknown',
    end_date_precision       TEXT DEFAULT 'unknown',
    status                   TEXT NOT NULL DEFAULT 'unknown',
    geometry                 geometry(Geometry, 4326),
    geometry_is_approximate  BOOLEAN DEFAULT FALSE,
    location_text            TEXT NOT NULL,
    source_id                TEXT NOT NULL,
    source_name              TEXT NOT NULL,
    source_page_row           TEXT,
    source_snippet            TEXT,
    source_url                TEXT,
    extraction_confidence     DOUBLE PRECISION,
    extraction_model          TEXT,
    extraction_model_version  TEXT,
    extracted_at               TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_projects_geometry ON projects USING GIST (geometry);
CREATE INDEX IF NOT EXISTS idx_projects_utility ON projects (utility_id);
CREATE INDEX IF NOT EXISTS idx_projects_dates ON projects (start_date, end_date);

CREATE TABLE IF NOT EXISTS matches (
    match_id                  TEXT PRIMARY KEY,
    project_a                 TEXT NOT NULL REFERENCES projects(project_id),
    project_b                 TEXT NOT NULL REFERENCES projects(project_id),
    distance_miles             DOUBLE PRECISION,
    overlap_days               INTEGER,
    near_boundary               BOOLEAN DEFAULT FALSE,
    boundary_distance_miles     DOUBLE PRECISION,
    reason_codes                TEXT[] NOT NULL DEFAULT '{}',
    spatial_threshold_miles      DOUBLE PRECISION,
    temporal_threshold_days      INTEGER,
    source_complete              BOOLEAN DEFAULT TRUE,
    computed_at                   TIMESTAMPTZ NOT NULL DEFAULT now(),
    review_status                 TEXT NOT NULL DEFAULT 'unreviewed'
);

CREATE INDEX IF NOT EXISTS idx_matches_projects ON matches (project_a, project_b);

-- Optional: boundary reference data for Seams Mode (state/utility/RTO lines)
CREATE TABLE IF NOT EXISTS boundaries (
    boundary_id    TEXT PRIMARY KEY,
    boundary_type  TEXT NOT NULL, -- 'state' | 'utility' | 'rto_iso' | 'planning_region'
    name           TEXT NOT NULL,
    geometry       geometry(Geometry, 4326)
);

CREATE INDEX IF NOT EXISTS idx_boundaries_geometry ON boundaries USING GIST (geometry);
