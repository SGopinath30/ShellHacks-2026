import { test } from "node:test";
import assert from "node:assert/strict";
import { projects } from "./fixtures";
import type { Project } from "./types";
import { buildMatches, parseCalendarDate, projectDateStatus } from "./utils";
import {
  addCalendarMonths,
  coordinationMatch,
  relationshipPhase,
  timingLabel,
  rankOpportunities,
} from "./coordination";

const a: Project = {
  ...projects[0],
  constructionStart: "2026-01-01",
  constructionEnd: "2026-08-31",
};
const b: Project = {
  ...projects[1],
  constructionStart: "2027-02-28",
  constructionEnd: "2027-06-01",
};
function assess(first = a, second = b) {
  return coordinationMatch(
    { ...buildMatches([a, b])[0], distanceMiles: 999, overlapDays: 999 },
    [first, second],
  )!;
}
test("six calendar months use nearest interval boundaries and month-end clamping", () => {
  assert.equal(
    new Date(addCalendarMonths(parseCalendarDate("2026-08-31")!, 6))
      .toISOString()
      .slice(0, 10),
    "2027-02-28",
  );
  assert.equal(
    new Date(addCalendarMonths(parseCalendarDate("2023-08-31")!, 6))
      .toISOString()
      .slice(0, 10),
    "2024-02-29",
  );
  const exact = assess();
  assert.equal(exact.eligible, true);
  assert.equal(exact.overlapDays, 0);
  assert.equal(exact.gapDays, 181);
  assert.equal(
    assess(a, { ...b, constructionStart: "2027-03-01" }).eligible,
    false,
  );
  // Long-running construction qualifies by overlap even if starts are far apart.
  const overlap = assess({
    ...a,
    constructionStart: "2020-01-01",
    constructionEnd: "2028-01-01",
  });
  assert.equal(overlap.eligible, true);
  assert.ok(overlap.overlapDays! > 0);
});
test("point relationship is shared with the map and ignores stale cached measurements", () => {
  const match = assess();
  assert.deepEqual(match.closestPoints, [a.location, b.location]);
  assert.equal(match.geometryBasis, "approximate-points");
  assert.ok(match.distanceMiles < 25);
  for (const miles of [24.999, 25.001]) {
    const first = { ...a, location: { longitude: 0, latitude: 0 } };
    const second = {
      ...b,
      location: {
        longitude: ((miles / 3958.7613) * 180) / Math.PI,
        latitude: 0,
      },
    };
    assert.equal(assess(first, second).eligible, miles < 25);
  }
  assert.equal(assess({ ...a, location: null }), null);
  assert.equal(assess(a, { ...b, utilityId: a.utilityId }), null);
});
test("missing, invalid and imprecise schedules never trigger alerts", () => {
  for (const change of [
    { constructionStart: null },
    { constructionEnd: null },
    { constructionStart: "2027-02-30" },
    { constructionEnd: "2026-01-01" },
    { datePrecision: "unknown" as const },
  ])
    assert.equal(assess(a, { ...b, ...change }).eligible, false);
  assert.equal(
    projectDateStatus({ ...b, constructionEnd: "2026-01-01" }, "2027-03-01"),
    "unknown",
  );
});
test("timeline distinguishes upcoming, active, and past without altering measured facts", () => {
  const overlap = assess(a, {
    ...b,
    constructionStart: "2026-05-01",
    constructionEnd: "2026-10-01",
  });
  assert.equal(relationshipPhase(overlap, "2026-04-30"), "upcoming");
  assert.equal(relationshipPhase(overlap, "2026-05-01"), "active");
  assert.equal(relationshipPhase(overlap, "2026-08-31"), "past");
  assert.equal(relationshipPhase(overlap, null), "unavailable");
  const gap = assess();
  assert.equal(relationshipPhase(gap, "2026-10-01"), "active");
  assert.equal(relationshipPhase(gap, "2027-03-01"), "past");
  assert.match(timingLabel(gap), /between windows/);
  const touching = assess(a, { ...b, constructionStart: a.constructionEnd });
  assert.equal(touching.overlapDays, 0);
  assert.equal(relationshipPhase(touching, a.constructionEnd), "active");
  assert.equal(relationshipPhase(touching, "2026-09-01"), "past");
  assert.equal(
    rankOpportunities([gap, overlap])[0].overlapDays,
    overlap.overlapDays,
  );
});
