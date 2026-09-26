import type { Filters, Match, Project } from "./types";
const DAY = 86400000;
export const DEFAULT_FILTERS: Filters = { distance: 3, overlap: 30 };
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
  const status = schedules.some((s) => s.status === "invalid")
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
      .filter((b) => a.utilityId !== b.utilityId)
      .map((b) => {
        const overlap = overlapDays(a, b);
        return {
          id: `${a.id}--${b.id}`,
          projectIds: [a.id, b.id] as [string, string],
          distanceMiles: distanceMiles(a, b),
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
    .map((m) => ({ ...m, overlapDays: assessMatch(m, projects).overlap }))
    .filter((m) => {
      const pair = resolvePair(m, projects);
      return (
        m.distanceMiles <= filters.distance &&
        (!pair || pair[0].utilityId !== pair[1].utilityId)
      );
    });
  return {
    opportunities: nearby.filter(
      (m) =>
        m.overlapDays !== null &&
        m.overlapDays > 0 &&
        m.overlapDays >= filters.overlap,
    ),
    unknown: nearby.filter((m) => m.overlapDays === null),
  };
}
export function resolveSelection(id: string | null, matches: Match[]) {
  return matches.some((m) => m.id === id) ? id : (matches[0]?.id ?? null);
}
export const utilityColor = (id: string) =>
  ({ lumen: "#24766c", tide: "#4d78b9", ember: "#c6863e" })[id] ?? "#64748b";
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
