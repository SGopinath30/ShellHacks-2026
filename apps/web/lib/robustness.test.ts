import { test } from "node:test";
import assert from "node:assert/strict";
import { projects } from "./fixtures";
import {
  buildMatches,
  distanceMiles,
  filterMatches,
  resolveSelection,
  utilityColor,
  utilityLegend,
  validLocation,
  safeSourceUrl,
  demoLabel,
} from "./utils";
import { projectBounds } from "./geo";

test("empty projects and changing utilities do not assume demo IDs", () => {
  assert.deepEqual(utilityLegend([]), []);
  assert.deepEqual(buildMatches([]), []);
  assert.equal(projectBounds([]), null);
  assert.equal(resolveSelection(null, []), null);
  assert.equal(demoLabel([]), "No project data");
  const other = [
    { ...projects[0], utilityId: "alpha", utilityName: "Alpha Utility" },
    { ...projects[1], utilityId: "beta", utilityName: "Beta Utility" },
  ];
  assert.deepEqual(
    utilityLegend(other).map((u) => u.id),
    ["alpha", "beta"],
  );
  assert.equal(utilityColor("alpha"), utilityColor("alpha"));
  assert.notEqual(utilityColor("alpha"), utilityColor("beta"));
  assert.equal(utilityColor("lumen"), "#24766c");
  assert.equal(buildMatches(other).length, 1);
});
test("zero coordinates are valid; missing, nonnumeric, nonfinite and out-of-range coordinates are excluded", () => {
  assert.equal(validLocation({ latitude: 0, longitude: 0 }), true);
  const bad = [
    null,
    { latitude: "0", longitude: 0 },
    { latitude: Infinity, longitude: 0 },
    { latitude: NaN, longitude: 0 },
    { latitude: 91, longitude: 0 },
    { latitude: 0, longitude: -181 },
  ];
  for (const location of bad) {
    assert.equal(validLocation(location), false);
    assert.equal(
      distanceMiles(
        { ...projects[0], location: location as never },
        projects[1],
      ),
      null,
    );
    assert.equal(
      buildMatches([
        { ...projects[0], location: location as never },
        projects[1],
      ]).length,
      0,
    );
  }
  const atZero = [
    { ...projects[0], location: { latitude: 0, longitude: 0 } },
    { ...projects[1], location: { latitude: 0, longitude: 0 } },
  ];
  assert.equal(distanceMiles(atZero[0],atZero[1]), 0);
  assert.equal(buildMatches(atZero).length, 1);
  const stale = {
    ...buildMatches(projects)[0],
    distanceMiles: 0,
    overlapDays: 999,
  };
  assert.deepEqual(
    filterMatches([stale], { distance: 12, overlap: 1 }, [
      { ...projects[0], location: null },
      projects[1],
    ]),
    { opportunities: [], unknown: [] },
  );
});
test("source links accept only HTTP(S) and synthetic label follows records", () => {
  assert.equal(
    safeSourceUrl("https://example.org/source"),
    "https://example.org/source",
  );
  assert.equal(
    safeSourceUrl("http://example.org/source"),
    "http://example.org/source",
  );
  for (const source of [
    null,
    "javascript:alert(1)",
    "data:text/plain,hello",
    "file:///tmp/data",
    "not a url",
  ])
    assert.equal(safeSourceUrl(source), null);
  assert.equal(demoLabel(projects), "Demo data");
  assert.equal(
    demoLabel([{ ...projects[0], synthetic: false }]),
    "Project data",
  );
  assert.equal(
    demoLabel([{ ...projects[0], synthetic: false }, projects[1]]),
    "Includes demo data",
  );
});
