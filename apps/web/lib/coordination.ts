import type { CoordinationMatch, Match, Project } from "./types";
import {
  constructionSchedule,
  distanceMiles,
  overlapDays,
  parseCalendarDate,
  resolvePair,
  validLocation,
} from "./utils";

export const ALERT_DISTANCE_MILES = 25;
export const ALERT_MONTHS = 6;
export const DEMO_DATE_RANGE = { min: "2026-01-01", max: "2030-12-31" };
const DAY = 86400000;
const iso = (timestamp: number) =>
  new Date(timestamp).toISOString().slice(0, 10);

/** Calendar months in UTC, clamped to the target month's final day. */
export function addCalendarMonths(timestamp: number, months: number) {
  const date = new Date(timestamp);
  const result = new Date(timestamp);
  result.setUTCDate(1);
  result.setUTCMonth(result.getUTCMonth() + months);
  const last = new Date(
    Date.UTC(result.getUTCFullYear(), result.getUTCMonth() + 1, 0),
  ).getUTCDate();
  result.setUTCDate(Math.min(date.getUTCDate(), last));
  return result.getTime();
}

/**
 * Distinct utilities, <=25 source-point miles, and <=6 calendar months between
 * nearest boundaries of valid construction intervals. Overlap/touching => gap 0.
 * Dates are start-inclusive/end-exclusive. No partial/invalid/approximate dates
 * trigger alerts. OSM road snapping NEVER supplies measured match coordinates.
 */
export function coordinationMatch(
  match: Match,
  projects: Project[],
): CoordinationMatch | null {
  const pair = resolvePair(match, projects);
  if (
    !pair ||
    pair[0].utilityId === pair[1].utilityId ||
    !validLocation(pair[0].location) ||
    !validLocation(pair[1].location)
  )
    return null;
  const distance = distanceMiles(...pair)!;
  const base = {
    ...match,
    distanceMiles: distance,
    overlapDays: overlapDays(...pair),
    closestPoints: [
      { ...pair[0].location },
      { ...pair[1].location },
    ] as CoordinationMatch["closestPoints"],
    geometryBasis: "approximate-points" as const,
  };
  const [a, b] = pair.map(constructionSchedule);
  if (
    a.status !== "valid" ||
    b.status !== "valid" ||
    pair.some((p) => p.datePrecision !== "day")
  ) {
    return {
      ...base,
      eligible: false,
      temporalStatus:
        a.status === "invalid" || b.status === "invalid"
          ? "invalid"
          : "incomplete",
      gapDays: null,
      focusWindow: null,
    };
  }
  const latestStart = Math.max(a.start, b.start);
  const earliestEnd = Math.min(a.end, b.end);
  const gap = Math.max(0, latestStart - earliestEnd);
  const within =
    gap === 0 || latestStart <= addCalendarMonths(earliestEnd, ALERT_MONTHS);
  return {
    ...base,
    eligible: distance <= ALERT_DISTANCE_MILES && within,
    temporalStatus: within ? "within-six-months" : "outside-six-months",
    gapDays: gap / DAY,
    focusWindow:
      gap === 0
        ? { start: iso(latestStart), end: iso(earliestEnd) }
        : { start: iso(earliestEnd), end: iso(latestStart) },
  };
}

/** Overlap is active during the shared interval; disjoint pairs during the gap.
 * Touching intervals have one focus date. Eligibility itself is date-independent.
 */
export function relationshipPhase(
  match: CoordinationMatch,
  selectedDate: string | null,
) {
  const target = parseCalendarDate(selectedDate);
  if (!match.eligible || !match.focusWindow || target === null)
    return "unavailable";
  const start = parseCalendarDate(match.focusWindow.start)!;
  const end = parseCalendarDate(match.focusWindow.end)!;
  if (target < start) return "upcoming";
  if (
    target > end ||
    (target === end && start !== end && (match.overlapDays ?? 0) > 0)
  )
    return "past";
  return "active";
}
export function timingLabel(match: CoordinationMatch) {
  if (match.source === "api") return `API tier: ${match.tier ?? "unavailable"}`;
  if (match.temporalStatus === "invalid") return "Schedule needs review";
  if (match.gapDays === null) return "Timing unknown";
  if ((match.overlapDays ?? 0) > 0) return `${match.overlapDays} days overlap`;
  if (match.gapDays === 0) return "Construction windows touch";
  return `${match.gapDays} days between windows`;
}
export function rankOpportunities(matches: CoordinationMatch[]) {
  return [...matches].sort(
    (a, b) =>
      a.distanceMiles - b.distanceMiles ||
      (b.overlapDays ?? 0) - (a.overlapDays ?? 0) ||
      (a.gapDays ?? Infinity) - (b.gapDays ?? Infinity) ||
      a.id.localeCompare(b.id),
  );
}
