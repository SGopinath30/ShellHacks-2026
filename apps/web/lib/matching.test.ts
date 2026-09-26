import { test } from "node:test";
import assert from "node:assert/strict";
import { projects } from "./fixtures";
import { completeA, completeB, scheduleCases } from "./schedule-cases";
import {
  assessMatch,
  buildMatches,
  constructionSchedule,
  DEFAULT_FILTERS,
  distanceMiles,
  filterMatches,
  formatDate,
  overlapDays,
  parseCalendarDate,
  resolvePair,
  resolveSelection,
} from "./utils";
for (const item of scheduleCases)
  test(item.name + ": schedule and stale match handling", () => {
    const snapshot = JSON.stringify(item.project);
    assert.equal(constructionSchedule(item.project).status, item.status);
    assert.equal(overlapDays(completeA, item.project), item.overlap);
    const records = [completeA, item.project];
    const stale = { ...buildMatches(records)[0], overlapDays: 999 };
    const result = filterMatches(
      [stale],
      { distance: 12, overlap: 1 },
      records,
    );
    assert.equal(
      result.opportunities.length,
      item.overlap !== null && item.overlap > 0 ? 1 : 0,
    );
    assert.equal(result.unknown.length, item.overlap === null ? 1 : 0);
    assert.equal(assessMatch(stale, records).overlap, item.overlap);
    assert.equal(JSON.stringify(item.project), snapshot);
  });
test("strict UTC calendar parsing and safe formatting", () => {
  for (const value of [
    "2027-02-30",
    "2027-02-29",
    "not-a-date",
    "2027-2-01",
    "2027-01",
    "2027-01-01T00:00:00Z",
    "",
  ]) {
    assert.equal(parseCalendarDate(value), null);
    assert.equal(formatDate(value), "Invalid date — review required");
  }
  assert.notEqual(parseCalendarDate("2028-02-29"), null);
  assert.equal(formatDate("2027-01-01"), "Jan 1, 2027");
  assert.equal(parseCalendarDate(null), null);
});
test("geographic distance, thresholds, same utilities, and selection", () => {
  const a = { ...completeA, location: { latitude: 0, longitude: 0 } };
  const b = { ...completeB, location: { latitude: 0, longitude: 1 } };
  assert.ok(Math.abs(distanceMiles(a, b) - 69.0934) < 0.01);
  assert.equal(distanceMiles(a, b), distanceMiles(b, a));
  assert.equal(distanceMiles(a, a), 0);
  const matches = buildMatches(projects);
  const result = filterMatches(matches, DEFAULT_FILTERS, projects);
  assert.ok(result.opportunities.some((m) => m.id === "P01--P02"));
  assert.ok(!matches.some((m) => m.id === "P01--P07"));
  assert.ok(
    !result.opportunities.some(
      (m) =>
        m.projectIds.includes("P04") ||
        m.projectIds.includes("P06") ||
        m.projectIds.includes("P05"),
    ),
  );
  const boundary = matches.find((m) => m.id === "P01--P02")!;
  assert.equal(
    filterMatches(
      [boundary],
      { distance: boundary.distanceMiles, overlap: boundary.overlapDays! },
      projects,
    ).opportunities.length,
    1,
  );
  assert.equal(
    filterMatches(
      [boundary],
      { distance: boundary.distanceMiles - 0.001, overlap: 1 },
      projects,
    ).opportunities.length,
    0,
  );
  assert.equal(
    filterMatches(
      [boundary],
      { distance: 12, overlap: boundary.overlapDays! + 1 },
      projects,
    ).opportunities.length,
    0,
  );
  const sameUtility = [
    completeA,
    { ...completeB, utilityId: completeA.utilityId },
  ];
  assert.equal(
    filterMatches(
      [buildMatches([completeA, completeB])[0]],
      { distance: 12, overlap: 1 },
      sameUtility,
    ).opportunities.length,
    0,
  );
  assert.equal(
    resolveSelection(result.opportunities[1].id, result.opportunities),
    result.opportunities[1].id,
  );
  assert.equal(
    resolveSelection("removed", result.opportunities),
    result.opportunities[0].id,
  );
  assert.equal(resolveSelection("removed", []), null);
});
test("missing reference is explicit, never an opportunity or partial pair", () => {
  const match = buildMatches([completeA, completeB])[0];
  assert.equal(resolvePair(match, [completeA]), null);
  assert.equal(assessMatch(match, [completeA]).status, "unavailable");
  const result = filterMatches([match], { distance: 12, overlap: 1 }, [
    completeA,
  ]);
  assert.equal(result.opportunities.length, 0);
  assert.equal(result.unknown.length, 1);
});
