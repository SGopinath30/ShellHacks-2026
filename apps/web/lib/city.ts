import {
  geoToScene,
  METERS_PER_SCENE_UNIT,
  projectBounds,
  type GeoPoint,
} from "./geo";
import type { Project } from "./types";
import { validLocation } from "./utils";

export type OsmRoad = { id: string; points: [number, number][]; kind: string };
export type OsmBuilding = {
  id: string;
  points: [number, number][];
  height: string | null;
  levels: string | null;
};
export type CityData = {
  source: string;
  bbox: [number, number, number, number];
  buildings: OsmBuilding[];
  roads: OsmRoad[];
};
export type ScenePoint = { x: number; y: number; z: number };
export type UtilityPath = { project: Project; points: ScenePoint[] };

/** Demo association only: OSM footprints do not establish utility ownership. */
export function utilityBuildingColors(projects: Project[], buildings: OsmBuilding[]) {
  const footprints = buildings.filter((building) =>
    building.points.length >= 3 && building.points.every(([longitude, latitude]) =>
      validLocation({ longitude, latitude }),
    ),
  ).map((building) => ({
    id: building.id,
    points: building.points.map(([lng, lat]) => geoToScene(lng, lat)),
  }));
  const assigned = new Map<string, { utilityId: string; distance: number }>();
  for (const project of [...projects].sort((a, b) => a.id.localeCompare(b.id))) {
    if (!validLocation(project.location)) continue;
    const p = geoToScene(project.location.longitude, project.location.latitude);
    let nearest: { id: string; distance: number } | null = null;
    for (const building of footprints) {
      let inside = false;
      let distance = Infinity;
      for (let i = 0; i < building.points.length; i++) {
        const a = building.points[i], b = building.points[(i + 1) % building.points.length];
        const closest = closestPointOnSegment(p, a, b);
        distance = Math.min(distance, Math.hypot(p.x - closest.x, p.z - closest.z));
        if ((a.z > p.z) !== (b.z > p.z) &&
          p.x < (b.x - a.x) * (p.z - a.z) / (b.z - a.z) + a.x) inside = !inside;
      }
      if (inside) distance = 0;
      if (distance * METERS_PER_SCENE_UNIT <= 200 && (!nearest || distance < nearest.distance)) {
        nearest = { id: building.id, distance };
      }
    }
    if (nearest && (!assigned.has(nearest.id) || nearest.distance < assigned.get(nearest.id)!.distance)) {
      assigned.set(nearest.id, { utilityId: project.utilityId, distance: nearest.distance });
    }
  }
  return new Map([...assigned].map(([id, value]) => [id, value.utilityId]));
}

export function usableRoads(data: CityData) {
  return data.roads.filter(
    (road) =>
      road.points.length >= 2 &&
      road.points.every((point) =>
        validLocation({ longitude: point[0], latitude: point[1] }),
      ),
  );
}
export function utilityPaths(
  projects: Project[],
  roads: OsmRoad[],
): UtilityPath[] {
  const bounds = projectBounds(projects);
  const clampX = (value: number) =>
    bounds ? Math.min(Math.max(value, bounds.minX), bounds.maxX) : value;
  const clampZ = (value: number) =>
    bounds ? Math.min(Math.max(value, bounds.minZ), bounds.maxZ) : value;

  const candidates = usableRoads({
    source: "",
    bbox: [0, 0, 0, 0],
    buildings: [],
    roads,
  }).map((road) => {
    const points = road.points.map(([lng, lat]) => {
      const point = geoToScene(lng, lat);
      return { x: clampX(point.x), y: point.y, z: clampZ(point.z) };
    });
    const length = points
      .slice(1)
      .reduce(
        (sum, p, i) => sum + Math.hypot(p.x - points[i].x, p.z - points[i].z),
        0,
      );
    return { points, length };
  });
  return projects.flatMap((project) => {
    if (!validLocation(project.location)) return [];
    const position = geoToScene(
      project.location.longitude,
      project.location.latitude,
    );
    let nearest: {
      points: ScenePoint[];
      index: number;
      distance: number;
      score: number;
    } | null = null;
    for (const { points, length } of candidates)
      for (let index = 0; index < points.length - 1; index++) {
        const a = points[index],
          b = points[index + 1];
        const dx = b.x - a.x,
          dz = b.z - a.z;
        const t = Math.max(
          0,
          Math.min(
            1,
            ((position.x - a.x) * dx + (position.z - a.z) * dz) /
              (dx * dx + dz * dz || 1),
          ),
        );
        const distance = Math.hypot(
          position.x - a.x - t * dx,
          position.z - a.z - t * dz,
        );
        const score = distance + Math.max(0, 40 - length);
        if (distance < 35 && (!nearest || score < nearest.score))
          nearest = { points, index, distance, score };
      }
    if (!nearest || nearest.distance > 35) return [];
    const segment = nearest.points.map((point) => ({
      ...point,
      x: clampX(point.x),
      z: clampZ(point.z),
      y: 0.2,
    }));
    return [{ project, points: segment }];
  });
}
function closestPointOnSegment(p: ScenePoint, a: ScenePoint, b: ScenePoint) {
  const dx = b.x - a.x,
    dz = b.z - a.z;
  const t = Math.max(
    0,
    Math.min(
      1,
      ((p.x - a.x) * dx + (p.z - a.z) * dz) / (dx * dx + dz * dz || 1),
    ),
  );
  return { x: a.x + t * dx, y: 0, z: a.z + t * dz };
}
export function nearestPathConnection(
  first: ScenePoint[],
  second: ScenePoint[],
) {
  if (first.length < 2 || second.length < 2) return null;
  let best: { a: ScenePoint; b: ScenePoint; distance: number } | null = null;
  for (let i = 0; i < first.length - 1; i++)
    for (let j = 0; j < second.length - 1; j++) {
      // Crossing segments meet inside both paths, not necessarily at a vertex.
      const p = first[i], q = second[j];
      const rx = first[i + 1].x - p.x, rz = first[i + 1].z - p.z;
      const sx = second[j + 1].x - q.x, sz = second[j + 1].z - q.z;
      const denominator = rx * sz - rz * sx;
      if (Math.abs(denominator) > 1e-10) {
        const t = ((q.x - p.x) * sz - (q.z - p.z) * sx) / denominator;
        const u = ((q.x - p.x) * rz - (q.z - p.z) * rx) / denominator;
        if (t >= 0 && t <= 1 && u >= 0 && u <= 1) {
          const point = { x: p.x + t * rx, y: 0, z: p.z + t * rz };
          return { a: point, b: point, distance: 0 };
        }
      }
      const candidates: [ScenePoint, ScenePoint][] = [
        [first[i], closestPointOnSegment(first[i], second[j], second[j + 1])],
        [
          first[i + 1],
          closestPointOnSegment(first[i + 1], second[j], second[j + 1]),
        ],
        [closestPointOnSegment(second[j], first[i], first[i + 1]), second[j]],
        [
          closestPointOnSegment(second[j + 1], first[i], first[i + 1]),
          second[j + 1],
        ],
      ];
      for (const [a, b] of candidates) {
        const distance = Math.hypot(a.x - b.x, a.z - b.z);
        if (!best || distance < best.distance) best = { a, b, distance };
      }
    }
  return best;
}
export function nearestPathMidpoint(
  first: ScenePoint[],
  second: ScenePoint[],
): ScenePoint | null {
  const best = nearestPathConnection(first, second);
  return best
    ? { x: (best.a.x + best.b.x) / 2, y: 0, z: (best.a.z + best.b.z) / 2 }
    : null;
}
export function buildingHeightMeters(building: OsmBuilding) {
  const tagged = Number.parseFloat(building.height ?? "");
  if (Number.isFinite(tagged) && tagged > 1 && tagged < 600) return tagged;
  const levels = Number.parseFloat(building.levels ?? "");
  if (Number.isFinite(levels) && levels > 0 && levels < 200)
    return levels * 3.2;
  let hash = 0;
  for (const ch of building.id) hash = (hash * 31 + ch.charCodeAt(0)) >>> 0;
  return 9 + (hash % 8) * 3;
}
export function parseCityData(raw: unknown): CityData {
  if (!raw || typeof raw !== "object")
    throw new Error("City geometry unavailable");
  const value = raw as Partial<CityData>;
  if (
    !Array.isArray(value.buildings) ||
    !Array.isArray(value.roads) ||
    !Array.isArray(value.bbox)
  )
    throw new Error("Invalid city geometry");
  return value as CityData;
}
export function projectPoint(project: Project): GeoPoint | null {
  return validLocation(project.location) ? project.location : null;
}
