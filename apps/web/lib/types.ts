/** Provisional frontend contracts. All current records are synthetic. */
export type Evidence = {
  field: string;
  sourceTitle: string;
  sourceUrl: string | null;
  pageOrRow: string | null;
  quote: string;
  synthetic: true;
};
export type Project = {
  id: string;
  utilityId: string;
  utilityName: string;
  name: string;
  type: string;
  status: string;
  location: { longitude: number; latitude: number };
  geometryQuality: "approximate-point";
  constructionStart: string | null;
  constructionEnd: string | null;
  inServiceDate: string | null;
  datePrecision: "day" | "unknown";
  evidence: Evidence[];
  synthetic: true;
};
export type Match = {
  id: string;
  projectIds: [string, string];
  distanceMiles: number;
  overlapDays: number | null;
  reasonCodes: string[];
};
export type Filters = { distance: number; overlap: number };
