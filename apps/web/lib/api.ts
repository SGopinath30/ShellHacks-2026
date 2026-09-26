import { projects } from "./fixtures";
import { buildMatches } from "./utils";
/** Fixture-only adapter; no backend endpoint or response contract exists yet.
 * Replace this adapter explicitly when contracts arrive. Never fall back on API failure.
 */
export function getDemoData() {
  return {
    projects,
    matches: buildMatches(projects),
    synthetic: true as const,
  };
}
