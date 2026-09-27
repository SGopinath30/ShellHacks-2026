import type { Project } from "./types";
import { validLocation } from "./utils";

// One fixed local tangent plane for every data layer. Units are eight meters.
export const SCENE_ORIGIN = { longitude: -80.205, latitude: 25.777 };
export const DEMO_CITY_BOUNDS = {
  west: -80.216,
  south: 25.768,
  east: -80.187,
  north: 25.794,
};
export const METERS_PER_SCENE_UNIT = 8;
const METERS_PER_DEGREE = 111_195;
const LONGITUDE_SCALE = Math.cos((SCENE_ORIGIN.latitude * Math.PI) / 180);
export const ROAD_Y_OFFSET = 0.02;
export const UTILITY_Y_OFFSET = 0.2;
export const CONFLICT_Y_OFFSET = UTILITY_Y_OFFSET + 0.15;

export type GeoPoint = { longitude: number; latitude: number };
export function geoToScene(longitude: number, latitude: number, altitude = 0) {
  return {
    x:
      ((longitude - SCENE_ORIGIN.longitude) *
        METERS_PER_DEGREE *
        LONGITUDE_SCALE) /
      METERS_PER_SCENE_UNIT,
    y: altitude,
    z:
      (-(latitude - SCENE_ORIGIN.latitude) * METERS_PER_DEGREE) /
      METERS_PER_SCENE_UNIT,
  };
}
export function sceneToGeo(x: number, z: number): GeoPoint {
  return {
    longitude:
      SCENE_ORIGIN.longitude +
      (x * METERS_PER_SCENE_UNIT) / (METERS_PER_DEGREE * LONGITUDE_SCALE),
    latitude:
      SCENE_ORIGIN.latitude - (z * METERS_PER_SCENE_UNIT) / METERS_PER_DEGREE,
  };
}
export function sceneProjects(projects: Project[]) {
  const valid = projects.filter((p) => validLocation(p.location));
  if (!valid.length) return [];
  // Frame projects in the bundled OSM city context; distant demo outliers
  // remain in the data but do not make the downtown network tiny.
  const nearby = valid.filter(
    (p) =>
      p.location!.longitude >= DEMO_CITY_BOUNDS.west &&
      p.location!.longitude <= DEMO_CITY_BOUNDS.east &&
      p.location!.latitude >= DEMO_CITY_BOUNDS.south &&
      p.location!.latitude <= DEMO_CITY_BOUNDS.north,
  );
  return nearby.length ? nearby : valid;
}
export function projectBounds(projects: Project[]) {
  const valid = sceneProjects(projects).filter((p) => validLocation(p.location));
  if (!valid.length) return null;
  const points = valid.map((p) =>
    geoToScene(p.location!.longitude, p.location!.latitude),
  );
  const minX = Math.min(...points.map((p) => p.x));
  const maxX = Math.max(...points.map((p) => p.x));
  const minZ = Math.min(...points.map((p) => p.z));
  const maxZ = Math.max(...points.map((p) => p.z));
  return {
    minX,
    maxX,
    minZ,
    maxZ,
    centerX: (minX + maxX) / 2,
    centerZ: (minZ + maxZ) / 2,
    span: Math.max(maxX - minX, maxZ - minZ, 90),
  };
}

export function clampScenePoint(
  point: { x: number; y: number; z: number },
  bounds: ReturnType<typeof projectBounds> | null,
) {
  if (!bounds) return point;
  return {
    x: Math.min(Math.max(point.x, bounds.minX), bounds.maxX),
    y: point.y,
    z: Math.min(Math.max(point.z, bounds.minZ), bounds.maxZ),
  };
}
export function osmBounds(projects: Project[]) {
  const focus = projectBounds(sceneProjects(projects));
  const center = focus
    ? sceneToGeo(focus.centerX, focus.centerZ)
    : SCENE_ORIGIN;
  // Bounded downtown extract. Its OSM geometry uses the same fixed projection.
  return {
    south: center.latitude - 0.011,
    west: center.longitude - 0.014,
    north: center.latitude + 0.011,
    east: center.longitude + 0.014,
  };
}
