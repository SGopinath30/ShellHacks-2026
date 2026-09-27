import type { Point, LineString } from "geojson";
import type { CoordinationMatch, Project } from "./types";
import {
  constructionSchedule,
  parseCalendarDate,
  validLocation,
} from "./utils";

export const API = "https://gridlock-api-production.up.railway.app/api/v1";
type RecordValue = Record<string, unknown>;
function record(value: unknown): RecordValue {
  if (!value || typeof value !== "object" || Array.isArray(value))
    throw new Error("Unexpected API response: expected an object.");
  return value as RecordValue;
}
const string = (value: unknown) => (typeof value === "string" ? value : null);
function required(value: unknown, field: string) {
  const result = string(value);
  if (!result) throw new Error(`Unexpected API response: missing ${field}.`);
  return result;
}
function list(value: unknown): unknown[] {
  if (!Array.isArray(value))
    throw new Error("Unexpected API response: expected a list.");
  return value;
}
export function parseGeometry(value: unknown): Point | LineString | null {
  if (!value || typeof value !== "object") return null;
  const g = record(value);
  const coordinate = (v: unknown): v is [number, number] =>
    Array.isArray(v) &&
    v.length >= 2 &&
    validLocation({ longitude: v[0], latitude: v[1] });
  if (g.type === "Point" && coordinate(g.coordinates))
    return { type: "Point", coordinates: g.coordinates };
  if (
    g.type === "LineString" &&
    Array.isArray(g.coordinates) &&
    g.coordinates.length >= 2 &&
    g.coordinates.every(coordinate)
  )
    return { type: "LineString", coordinates: g.coordinates };
  return null;
}
export function adaptProject(value: unknown): Project {
  const p = record(value);
  const s = p.schedule ? record(p.schedule) : {};
  const exact = (v: unknown) => {
    if (!v || typeof v !== "object") return null;
    const b = record(v);
    return b.earliest === b.latest ? string(b.earliest) : null;
  };
  const construction = s.type === "CONSTRUCTION_WINDOW";
  const start = construction ? exact(s.start) : null;
  const end = construction ? exact(s.end_exclusive) : null;
  const geometry = parseGeometry(p.geometry);
  const synthetic = p.is_fixture === true;
  const boundsNote = (value: unknown) => {
    if (!value || typeof value !== "object") return "not provided";
    const b = record(value);
    return `${string(b.earliest) ?? "unknown"} to ${string(b.latest) ?? "unknown"}`;
  };
  return {
    id: required(p.project_id, "project_id"),
    utilityId: required(p.utility_id, "utility_id"),
    utilityName:
      string(p.utility_name) ??
      required(p.utility_id, "utility_id").replaceAll("_", " "),
    name: required(p.project_name, "project_name"),
    type: string(p.project_type) ?? "unknown",
    status: string(p.status) ?? "unknown",
    geometry,
    location:
      geometry?.type === "Point"
        ? {
            longitude: geometry.coordinates[0],
            latitude: geometry.coordinates[1],
          }
        : null,
    locationText: string(p.location_text) ?? undefined,
    geometryQuality: string(p.geometry_quality) ?? "UNRESOLVED",
    validationState: string(p.validation_state) ?? "UNRESOLVED",
    constructionStart: start,
    constructionEnd: end,
    inServiceDate:
      s.type === "IN_SERVICE_GAP" ? string(s.in_service_date) : null,
    datePrecision:
      parseCalendarDate(start) !== null && parseCalendarDate(end) !== null
        ? "day"
        : "unknown",
    scheduleNote:
      construction && (!start || !end)
        ? `Uncertain construction dates. Start: ${boundsNote(s.start)}; end (exclusive): ${boundsNote(s.end_exclusive)}. No exact window inferred.`
        : undefined,
    evidence: (Array.isArray(p.evidence) ? p.evidence : []).map((value) => {
      const e = record(value);
      return {
        field: "Source record",
        sourceTitle: string(e.source_name) ?? "Unnamed source",
        sourceUrl: string(e.source_url),
        pageOrRow: string(e.page_or_row),
        quote: string(e.snippet) ?? "No source excerpt provided.",
        synthetic,
      };
    }),
    synthetic,
  };
}
export function adaptOpportunity(
  value: unknown,
  projects: Project[],
): CoordinationMatch {
  const m = record(value);
  const embedded = Array.isArray(m.projects)
    ? m.projects
    : [m.project_a, m.project_b];
  const ids = embedded.map((v) =>
    typeof v === "string"
      ? v
      : required(record(v).project_id, "opportunity project_id"),
  );
  if (ids.length !== 2 || ids[0] === ids[1])
    throw new Error(
      "Unexpected API response: opportunity needs two distinct projects.",
    );
  const pair = ids.map((id) => projects.find((p) => p.id === id));
  if (!pair[0] || !pair[1])
    throw new Error(
      "An API opportunity references a project missing from the project list.",
    );
  const meters = record(m.distance).meters;
  if (typeof meters !== "number" || !Number.isFinite(meters) || meters < 0)
    throw new Error("Unexpected API response: invalid distance.meters.");
  // The service owns ranking and tier. Do not run the fixture matching rules here.
  const points =
    pair[0].location && pair[1].location
      ? ([pair[0].location, pair[1].location] as NonNullable<
          CoordinationMatch["closestPoints"]
        >)
      : null;
  const [a, b] = pair.map((p) => constructionSchedule(p!));
  // A display-only overlap of exact construction dates; never a ranking or tier input.
  const focusWindow =
    a.status === "valid" &&
    b.status === "valid" &&
    Math.max(a.start, b.start) < Math.min(a.end, b.end)
      ? {
          start: new Date(Math.max(a.start, b.start))
            .toISOString()
            .slice(0, 10),
          end: new Date(Math.min(a.end, b.end)).toISOString().slice(0, 10),
        }
      : null;
  return {
    id: required(m.pair_id, "pair_id"),
    projectIds: [ids[0], ids[1]],
    distanceMiles: meters / 1609.344,
    tier: required(m.tier, "tier"),
    source: "api",
    reasonCodes: [],
    overlapDays: focusWindow
      ? (Date.parse(focusWindow.end) - Date.parse(focusWindow.start)) / 86400000
      : null,
    gapDays: null,
    eligible: true,
    temporalStatus: focusWindow ? "within-six-months" : "incomplete",
    focusWindow,
    closestPoints: points,
    geometryBasis: points ? "source-points" : "unavailable",
  };
}
export type LiveData = {
  projects: Project[];
  matches: CoordinationMatch[];
  featureCount: number;
};
export async function getData(
  path: string,
  signal?: AbortSignal,
): Promise<unknown> {
  const response = await fetch(`${API}${path}`, {
    signal: signal
      ? AbortSignal.any([signal, AbortSignal.timeout(20000)])
      : AbortSignal.timeout(20000),
  });
  if (!response.ok) throw new Error(`API error: ${response.status} (${path})`);
  return response.json();
}
export async function loadLiveData(signal?: AbortSignal): Promise<LiveData> {
  const [rawProjects, rawMap, rawMatches] = await Promise.all([
    getData("/projects", signal),
    getData("/projects/geojson", signal),
    getData("/opportunities", signal),
  ]);
  const map = record(rawMap);
  if (map.type !== "FeatureCollection")
    throw new Error("Unexpected API map response.");
  const features = list(map.features).map(record);
  const projects = list(rawProjects).map(adaptProject);
  if (new Set(projects.map((p) => p.id)).size !== projects.length)
    throw new Error("API returned duplicate project IDs.");
  // GeoJSON is authoritative for the map. No synthetic geometry fallback.
  for (const p of projects) {
    const feature = features.find(
      (f) =>
        f.id === p.id ||
        (f.properties && record(f.properties).project_id === p.id),
    );
    p.geometry = feature ? parseGeometry(feature.geometry) : null;
    p.location =
      p.geometry?.type === "Point"
        ? {
            longitude: p.geometry.coordinates[0],
            latitude: p.geometry.coordinates[1],
          }
        : null;
  }
  const matches = list(rawMatches).map((m) => adaptOpportunity(m, projects));
  if (new Set(matches.map((m) => m.id)).size !== matches.length)
    throw new Error("API returned duplicate opportunity IDs.");
  return { projects, matches, featureCount: features.length };
}
export async function loadOpportunity(
  id: string,
  projects: Project[],
  signal?: AbortSignal,
) {
  const raw = record(
    await getData(`/opportunities/${encodeURIComponent(id)}`, signal),
  );
  const embedded = Array.isArray(raw.projects)
    ? raw.projects
    : [raw.project_a, raw.project_b];
  const updates = embedded
    .filter((p) => p && typeof p === "object")
    .map(adaptProject);
  const merged = projects.map((p) => {
    const update = updates.find((v) => v.id === p.id);
    return update
      ? { ...update, geometry: p.geometry, location: p.location }
      : p;
  });
  const match = adaptOpportunity(raw, merged);
  if (match.id !== id)
    throw new Error("The API returned details for a different opportunity.");
  return { match, projects: merged };
}
