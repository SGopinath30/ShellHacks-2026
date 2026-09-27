/** Presentation contracts shared by live API records and explicit demo fixtures. */
export type Evidence = {
  field: string;
  sourceTitle: string;
  sourceUrl: string | null;
  pageOrRow: string | null;
  quote: string;
  synthetic: boolean;
};
export type Project = {
  id: string;
  utilityId: string;
  utilityName: string;
  name: string;
  type: string;
  status: string;
  location: { longitude: number; latitude: number } | null;
  geometryQuality: string;
  geometry?: import("geojson").Point | import("geojson").LineString | null;
  validationState?: string;
  locationText?: string;
  scheduleNote?: string;
  constructionStart: string | null;
  constructionEnd: string | null;
  inServiceDate: string | null;
  depthMeters?: number | null;
  datePrecision: "day" | "unknown";
  evidence: Evidence[];
  synthetic: boolean;
};
export type Match = {
  id: string;
  projectIds: [string, string];
  distanceMiles: number;
  overlapDays: number | null;
  reasonCodes: string[];
  source?: "api";
  tier?: string;
};
export type Filters = { distance: number; overlap: number };

/** Frontend-only relationship result; points reflect the source geometry. */
export type CoordinationMatch = Match & {
  closestPoints:
    [NonNullable<Project["location"]>, NonNullable<Project["location"]>] | null;
  geometryBasis: "approximate-points" | "source-points" | "unavailable";
  eligible: boolean;
  temporalStatus:
    "within-six-months" | "outside-six-months" | "incomplete" | "invalid";
  gapDays: number | null;
  focusWindow: { start: string; end: string } | null;
};
