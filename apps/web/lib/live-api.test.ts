import test from "node:test";
import assert from "node:assert/strict";
import {
  adaptProject,
  adaptOpportunity,
  parseGeometry,
  loadLiveData,
  loadOpportunity,
  API,
} from "./live-api";

const raw = {
  project_id: "DELL-001",
  utility_id: "UTILITY_A",
  project_name: "Example Substation Expansion",
  project_type: "substation",
  status: "planned",
  location_text: "Savannah, Georgia",
  geometry: { type: "Point", coordinates: [-81.05, 32] },
  geometry_origin: "CENTER_POINT",
  geometry_quality: "APPROXIMATE",
  validation_state: "NEEDS_REVIEW",
  schedule: { type: "IN_SERVICE_GAP", in_service_date: "2027-06-01" },
  evidence: [
    {
      source_id: "filing-001",
      source_name: "Example utility filing",
      page_or_row: "Page 4",
    },
  ],
};
const other = { ...raw, project_id: "OTHER", utility_id: "UTILITY_B" };
const opportunity = {
  pair_id: "DELL-001/OTHER +",
  projects: [raw, other],
  distance: { meters: 1609.344 },
  tier: "POSSIBLE",
};

test("user's in-service example retains evidence and review flags, without a construction interval", () => {
  const p = adaptProject(raw);
  assert.equal(p.constructionStart, null);
  assert.equal(p.constructionEnd, null);
  assert.equal(p.inServiceDate, "2027-06-01");
  assert.equal(p.datePrecision, "unknown");
  assert.equal(p.validationState, "NEEDS_REVIEW");
  assert.equal(p.evidence[0].pageOrRow, "Page 4");
  assert.equal(p.synthetic, false);
});
test("exact bounds render construction dates while uncertain bounds stay uncertain", () => {
  const schedule = {
    type: "CONSTRUCTION_WINDOW",
    start: { earliest: "2027-01-01", latest: "2027-01-01" },
    end_exclusive: { earliest: "2027-06-01", latest: "2027-06-01" },
  };
  assert.equal(adaptProject({ ...raw, schedule }).datePrecision, "day");
  const uncertain = adaptProject({
    ...raw,
    schedule: {
      ...schedule,
      start: { earliest: "2027-01-01", latest: "2027-03-01" },
    },
  });
  assert.equal(uncertain.constructionStart, null);
  assert.match(uncertain.scheduleNote!, /2027-03-01/);
});
test("backend distance and tier survive instead of recalculating from identical points", () => {
  const match = adaptOpportunity(opportunity, [
    adaptProject(raw),
    adaptProject(other),
  ]);
  assert.equal(match.distanceMiles, 1);
  assert.equal(match.tier, "POSSIBLE");
  assert.equal(match.focusWindow, null);
  assert.equal(match.eligible, true);
});
test("missing project references and invalid measurements fail clearly", () => {
  assert.throws(
    () => adaptOpportunity(opportunity, [adaptProject(raw)]),
    /missing from/,
  );
  assert.throws(
    () =>
      adaptOpportunity({ ...opportunity, distance: { meters: -1 } }, [
        adaptProject(raw),
        adaptProject(other),
      ]),
    /invalid distance/,
  );
});
test("map validates coordinates, preserves lines and never invents centroids", () => {
  assert.equal(parseGeometry({ type: "Point", coordinates: [181, 32] }), null);
  assert.equal(parseGeometry({ type: "Point", coordinates: ["0", 0] }), null);
  assert.ok(parseGeometry({ type: "Point", coordinates: [0, 0] }));
  const line = {
    type: "LineString",
    coordinates: [
      [-81, 32],
      [-80, 33],
    ],
  };
  assert.deepEqual(parseGeometry(line), line);
  assert.equal(adaptProject({ ...raw, geometry: line }).location, null);
});
test("three endpoints preserve API order and use GeoJSON geometry, detail URL is encoded", async () => {
  const original = globalThis.fetch;
  const urls: string[] = [];
  globalThis.fetch = async (input) => {
    const url = String(input);
    urls.push(url);
    const result = url.endsWith("/projects")
      ? [raw, other]
      : url.endsWith("/geojson")
        ? {
            type: "FeatureCollection",
            features: [
              {
                type: "Feature",
                properties: { project_id: raw.project_id },
                geometry: { type: "Point", coordinates: [-82, 33] },
              },
            ],
          }
        : url.endsWith("/opportunities")
          ? [
              opportunity,
              { ...opportunity, pair_id: "second", distance: { meters: 1 } },
            ]
          : opportunity;
    return Response.json(result);
  };
  try {
    const data = await loadLiveData();
    assert.deepEqual(
      data.matches.map((m) => m.id),
      [opportunity.pair_id, "second"],
    );
    assert.deepEqual(data.projects[0].location, {
      longitude: -82,
      latitude: 33,
    });
    assert.equal(data.projects[1].geometry, null);
    const detail = await loadOpportunity(opportunity.pair_id, data.projects);
    assert.equal(detail.match.id, opportunity.pair_id);
    assert.equal(
      urls.at(-1),
      `${API}/opportunities/${encodeURIComponent(opportunity.pair_id)}`,
    );
  } finally {
    globalThis.fetch = original;
  }
});
test("HTTP failures remain errors; there is no fixture fallback", async () => {
  const original = globalThis.fetch;
  globalThis.fetch = async () => new Response("Unavailable", { status: 503 });
  try {
    await assert.rejects(loadLiveData(), /API error: 503/);
  } finally {
    globalThis.fetch = original;
  }
});
