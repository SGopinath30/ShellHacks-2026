import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { projects } from "./fixtures";
import {
  geoToScene,
  sceneToGeo,
  ROAD_Y_OFFSET,
  UTILITY_Y_OFFSET,
  CONFLICT_Y_OFFSET,
  sceneProjects,
  projectBounds,
  clampScenePoint,
} from "./geo";
import {
  parseCityData,
  utilityPaths,
  nearestPathMidpoint,
  nearestPathConnection,
  buildingHeightMeters,
  utilityBuildingColors,
} from "./city";

const city = parseCityData(
  JSON.parse(readFileSync("public/city-osm.json", "utf8")),
);

test("demo building highlights cover each utility and exclude unmappable or distant projects", () => {
  const associations = utilityBuildingColors(projects, city.buildings);
  assert.deepEqual(new Set(associations.values()), new Set(projects.map((p) => p.utilityId)));
  assert.ok([...associations.keys()].every((id) => city.buildings.some((b) => b.id === id)));
  assert.equal(utilityBuildingColors([{ ...projects[0], location: null }], city.buildings).size, 0);
  assert.equal(utilityBuildingColors([{ ...projects[0], location: { latitude: 0, longitude: 0 } }], city.buildings).size, 0);
  assert.deepEqual(utilityBuildingColors([...projects].reverse(), city.buildings), associations);
});

test("selected links join the nearest path positions and handle crossings", () => {
  const point = (x: number, z: number) => ({ x, y: 0.2, z });
  const first = [point(0, 0), point(10, 0)];
  const separated = nearestPathConnection(first, [point(5, 4), point(5, 8)]);
  assert.ok(separated);
  assert.equal(separated.distance, 4);
  assert.equal(separated.a.x, 5);
  assert.equal(separated.a.z, 0);
  assert.equal(separated.b.x, 5);
  assert.equal(separated.b.z, 4);
  const crossing = nearestPathConnection(first, [point(5, -4), point(5, 4)]);
  assert.equal(crossing?.distance, 0);
  assert.deepEqual(crossing?.a, { x: 5, y: 0, z: 0 });
  assert.equal(nearestPathConnection([], first), null);
});
test("one reversible geographic projection anchors all scene layers", () => {
  const origin = geoToScene(-80.205, 25.777);
  assert.equal(origin.x, 0);
  assert.equal(origin.y, 0);
  assert.ok(Math.abs(origin.z) < 1e-12);
  const east = geoToScene(-80.204, 25.777),
    north = geoToScene(-80.205, 25.778);
  assert.ok(east.x > 0 && north.z < 0);
  const point = geoToScene(-80.199, 25.781, UTILITY_Y_OFFSET);
  assert.ok(Math.abs(sceneToGeo(point.x, point.z).longitude + 80.199) < 1e-9);
  assert.ok(Math.abs(sceneToGeo(point.x, point.z).latitude - 25.781) < 1e-9);
  assert.ok(
    ROAD_Y_OFFSET < UTILITY_Y_OFFSET && UTILITY_Y_OFFSET < CONFLICT_Y_OFFSET,
  );
});
test("bundled OSM city contains real roads and polygon buildings in project area", () => {
  assert.equal(city.source, "OpenStreetMap contributors");
  assert.ok(city.buildings.length > 2000 && city.roads.length > 3000);
  assert.ok(city.buildings.some((building) => building.points.length >= 4));
  assert.ok(
    city.buildings.every((building) => buildingHeightMeters(building) > 0),
  );
  const focus = sceneProjects(projects);
  assert.ok(focus.some((p) => p.utilityId === "ember"));
  assert.ok(!focus.some((p) => p.id === "P06"));
  assert.ok((projectBounds(projects)?.span ?? 0) < 400);
  assert.ok((projectBounds(focus)?.span ?? 0) < 400);
});
test("city roads and building footprints stay within the active scene footprint", () => {
  const bounds = projectBounds(projects);
  assert.ok(bounds);
  for (const road of city.roads) {
    for (const [longitude, latitude] of road.points) {
      const point = clampScenePoint(geoToScene(longitude, latitude), bounds);
      assert.ok(
        point.x >= bounds.minX && point.x <= bounds.maxX &&
          point.z >= bounds.minZ && point.z <= bounds.maxZ,
        `Road point ${longitude}, ${latitude} lies outside the scene bounds`,
      );
    }
  }
});
test("utility overlays follow OSM road coordinates and conflict midpoint uses nearest path positions", () => {
  const paths = utilityPaths(projects, city.roads);
  const first = paths.find((path) => path.project.id === "P01");
  const second = paths.find((path) => path.project.id === "P02");
  const third = paths.find((path) => path.project.id === "P03");
  assert.ok(first && second && third);
  assert.ok(
    first.points.length >= 2 &&
      first.points.every((point) => point.y === UTILITY_Y_OFFSET),
  );
  const conflict = nearestPathMidpoint(first.points, second.points);
  assert.ok(
    conflict && Number.isFinite(conflict.x) && Number.isFinite(conflict.z),
  );
  const projectMid = {
    x:
      (geoToScene(
        projects[0].location!.longitude,
        projects[0].location!.latitude,
      ).x +
        geoToScene(
          projects[1].location!.longitude,
          projects[1].location!.latitude,
        ).x) /
      2,
    z:
      (geoToScene(
        projects[0].location!.longitude,
        projects[0].location!.latitude,
      ).z +
        geoToScene(
          projects[1].location!.longitude,
          projects[1].location!.latitude,
        ).z) /
      2,
  };
  assert.ok(
    Math.hypot(conflict.x - projectMid.x, conflict.z - projectMid.z) > 0.01,
  );
  assert.equal(
    utilityPaths([{ ...projects[0], location: null }], city.roads).length,
    0,
  );
});
