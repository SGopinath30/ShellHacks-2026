export type Evidence = {
  source_id: string
  source_name: string
  source_url?: string | null
  page_or_row?: string | null
  snippet?: string | null
}

export type Geometry =
  | { type: 'Point'; coordinates: [number, number] }
  | { type: 'LineString'; coordinates: [number, number][] }

export type Project = {
  project_id: string
  utility_id: string
  project_name: string
  project_type: string
  status: string
  location_text: string
  geometry: Geometry | null
  geometry_origin: string
  geometry_quality: string
  validation_state: string
  version_id: string
  version_number: number
  upstream_project_version_id?: string | null
  upstream_candidate_id?: string | null
  evidence: Evidence[]
  is_fixture: boolean
  schedule?: Record<string, unknown>
}

export type ReviewRow = {
  project: Project
  qualified_ready: boolean
  matching_eligible: boolean
  blockers: string[]
  coordinate_role: string
}

export type ReviewQueue = { total: number; projects: ReviewRow[] }

export type PairAssessment = {
  project_a: { project_id: string; blockers: string[]; coordinate_role: string; qualified_ready: boolean }
  project_b: { project_id: string; blockers: string[]; coordinate_role: string; qualified_ready: boolean }
  distance: { meters: number; miles: number; kind: string; within_configured_maximum: boolean } | null
  maximum_meters: number
  blockers: string[]
  qualifies: boolean
}

export type Opportunity = {
  pair_id: string
  project_a: string
  project_b: string
  projects: Project[]
  distance: { meters: number; display_miles: number; method: string; geometry_quality: string; engine_version: string }
  tier: string
  possible_coordination_areas: string[]
  temporal_relationship: Record<string, unknown>
  temporal_strength: string
  is_fixture: boolean
  decision_context_hash?: string
  impact_estimate?: unknown | null
  impact_model_version?: string | null
}

export type QualifiedPairs = {
  maximum_meters: number
  total: number
  opportunities: Opportunity[]
}

export type LedgerEvent = {
  event_id: string
  event_type: string
  actor_id: string
  actor_role: string
  reason: string | null
  occurred_at: string
  snapshot: Opportunity
  details: Record<string, unknown>
}

export type Ledger = {
  pair_id: string
  current_status: string
  requires_re_review: boolean
  events: LedgerEvent[]
}
