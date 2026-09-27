import type { Filters, Match, Project } from "./types";
const DAY = 86400000;
export type ProjectDateStatus = "planned" | "active" | "completed" | "unknown";
export const DEFAULT_FILTERS: Filters = { distance: 3, overlap: 30 };
export const DEFAULT_PIPE_DEPTH_METERS = 2.5;
export const UTILITY_DEPTHS_METERS: Record<string, number> = {
  lumen: 4.5,
  tide: 3.4,
  ember: 1.8,
};
export function validLocation(location: unknown): location is NonNullable<Project['location']> {
  if (typeof location !== 'object' || location === null) return false;
  const { latitude, longitude } = location as Record<string, unknown>;
  return typeof latitude === 'number' && Number.isFinite(latitude) && latitude >= -90 && latitude <= 90 && typeof longitude === 'number' && Number.isFinite(longitude) && longitude >= -180 && longitude <= 180;
}
export function utilityLegend(projects: Project[]) {
  return [...new Map(projects.map(p => [p.utilityId, { id: p.utilityId, name: p.utilityName, color: utilityColor(p.utilityId) }])).values()];
}
export function demoLabel(projects: Project[]) {
  const count = projects.filter(p => p.synthetic === true).length;
  return !projects.length ? 'No project data' : count === projects.length ? 'Demo data' : count ? 'Includes demo data' : 'Project data';
}
export function safeSourceUrl(value: string | null): string | null {
  if (!value) return null;
  try { const url = new URL(value); return ['http:', 'https:'].includes(url.protocol) ? url.href : null; } catch { return null; }
}
export function parseCalendarDate(value: string | null): number | null {
  if (value === null || !/^\d{4}-\d{2}-\d{2}$/.test(value)) return null;
  const timestamp = Date.parse(`${value}T00:00:00Z`);
  return Number.isFinite(timestamp) &&
    new Date(timestamp).toISOString().slice(0, 10) === value
    ? timestamp
    : null;
}
export type ConstructionSchedule =
  | { status: "valid"; start: number; end: number }
  | { status: "incomplete"; start: number | null; end: number | null }
  | { status: "invalid"; start: number | null; end: number | null };
export function constructionSchedule(project: Project): ConstructionSchedule {
  const start = parseCalendarDate(project.constructionStart);
  const end = parseCalendarDate(project.constructionEnd);
  if (
    (project.constructionStart !== null && start === null) ||
    (project.constructionEnd !== null && end === null) ||
    (start !== null && end !== null && end <= start)
  )
    return { status: "invalid", start, end };
  if (start === null || end === null)
    return { status: "incomplete", start, end };
  return { status: "valid", start, end };
}
export function projectDepthMeters(project: Project): number {
  if (
    typeof project.depthMeters === "number" &&
    Number.isFinite(project.depthMeters) &&
    project.depthMeters > 0
  ) {
    return project.depthMeters;
  }
  return UTILITY_DEPTHS_METERS[project.utilityId] ?? DEFAULT_PIPE_DEPTH_METERS;
}
export function dateRangeForProjects(projects: Project[]) {
  const values = projects
    .flatMap((project) => [project.constructionStart, project.constructionEnd])
    .map(parseCalendarDate)
    .filter((value): value is number => value !== null);
  if (!values.length) {
    return { min: null, max: null } as const;
  }
  return {
    min: new Date(Math.min(...values)).toISOString().slice(0, 10),
    max: new Date(Math.max(...values)).toISOString().slice(0, 10),
  } as const;
}
export function projectDateStatus(
  project: Project,
  selectedDate: string | null,
): ProjectDateStatus {
  const target = selectedDate === null ? null : parseCalendarDate(selectedDate);
  if (target === null) return "unknown";
  if (constructionSchedule(project).status !== "valid" || project.datePrecision !== "day") return "unknown";
  const start = parseCalendarDate(project.constructionStart);
  const end = parseCalendarDate(project.constructionEnd);
  if (start === null || end === null) return "unknown";
  if (target < start) return "planned";
  if (target >= end) return "completed";
  return "active";
}
export function resolvePair(
  match: Match,
  projects: Project[],
): [Project, Project] | null {
  const a = projects.find((p) => p.id === match.projectIds[0]);
  const b = projects.find((p) => p.id === match.projectIds[1]);
  return a && b ? [a, b] : null;
}
/** Demo-only derivation: never trust cached overlap values over source schedules. */
export function assessMatch(match: Match, projects: Project[]) {
  const pair = resolvePair(match, projects);
  if (!pair)
    return { pair: null, status: "unavailable" as const, overlap: null };
  const schedules = pair.map(constructionSchedule);
  const overlap = overlapDays(...pair);
  const status = !validLocation(pair[0].location) || !validLocation(pair[1].location)
    ? "unavailable-location"
    : schedules.some((s) => s.status === "invalid")
    ? "invalid"
    : schedules.some((s) => s.status === "incomplete")
      ? "incomplete"
      : overlap! > 0 && pair[0].utilityId !== pair[1].utilityId
        ? "overlap"
        : "no-overlap";
  return { pair, status, overlap };
}
export function overlapDays(a: Project, b: Project): number | null {
  const first = constructionSchedule(a),
    second = constructionSchedule(b);
  if (first.status !== "valid" || second.status !== "valid") return null;
  return Math.max(
    0,
    (Math.min(first.end, second.end) - Math.max(first.start, second.start)) /
      DAY,
  );
}
export function distanceMiles(a: Project, b: Project) {
  if (!validLocation(a.location) || !validLocation(b.location)) return null;
  const rad = (n: number) => (n * Math.PI) / 180;
  const x =
    Math.sin(rad(b.location.latitude - a.location.latitude) / 2) ** 2 +
    Math.cos(rad(a.location.latitude)) *
      Math.cos(rad(b.location.latitude)) *
      Math.sin(rad(b.location.longitude - a.location.longitude) / 2) ** 2;
  return 3958.7613 * 2 * Math.asin(Math.sqrt(Math.min(1, x)));
}
export function buildMatches(projects: Project[]): Match[] {
  return projects.flatMap((a, i) =>
    projects
      .slice(i + 1)
      .filter((b) => a.utilityId !== b.utilityId && validLocation(a.location) && validLocation(b.location))
      .map((b) => {
        const overlap = overlapDays(a, b);
        return {
          id: `${a.id}--${b.id}`,
          projectIds: [a.id, b.id] as [string, string],
          distanceMiles: distanceMiles(a, b)!,
          overlapDays: overlap,
          reasonCodes: [
            overlap === null
              ? "TIMING_UNKNOWN"
              : overlap > 0
                ? "CONSTRUCTION_OVERLAP"
                : "NO_OVERLAP",
          ],
        };
      }),
  );
}
export function filterMatches(
  matches: Match[],
  filters: Filters,
  projects: Project[],
) {
  const nearby = matches
    .map((m) => {
      const assessment = assessMatch(m, projects);
      const pair = resolvePair(m, projects);
      return {
        ...m,
        overlapDays: assessment.overlap,
        distanceMiles: pair ? distanceMiles(...pair)! : m.distanceMiles,
        pair,
      };
    })
    .filter((m) => {
      const pair = m.pair;
      if (pair === null) return true;
      if (!validLocation(pair[0].location) || !validLocation(pair[1].location)) return false;
      if (pair[0].utilityId === pair[1].utilityId) return false;
      return m.distanceMiles <= filters.distance;
    });

  return {
    opportunities: nearby.filter(
      (m) =>
        m.pair !== null &&
        m.overlapDays !== null &&
        m.overlapDays > 0 &&
        m.overlapDays >= filters.overlap,
    ),
    unknown: nearby.filter((m) => m.pair === null || m.overlapDays === null),
  };
}
export function resolveSelection(id: string | null, matches: Match[]) {
  return matches.some((m) => m.id === id) ? id : (matches[0]?.id ?? null);
}
export const utilityColor = (id: string) => {
  const known = ({ lumen: "#24766c", tide: "#4d78b9", ember: "#c6863e" })[id];
  if (known) return known;
  let hash = 0;
  for (const char of id) hash = (Math.imul(hash, 31) + char.charCodeAt(0)) >>> 0;
  return `hsl(${hash % 360}, 42%, 42%)`;
};
export const formatDate = (date: string | null) => {
  const timestamp = parseCalendarDate(date);
  return timestamp !== null
    ? new Date(timestamp).toLocaleDateString("en-US", {
        month: "short",
        day: "numeric",
        year: "numeric",
        timeZone: "UTC",
      })
    : date === null
      ? "Not provided"
      : "Invalid date — review required";
};
