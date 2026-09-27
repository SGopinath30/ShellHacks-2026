"use client";
import { useEffect, useMemo } from "react";
import * as THREE from "three";
import { mergeGeometries } from "three/examples/jsm/utils/BufferGeometryUtils.js";
import {
  clampScenePoint,
  geoToScene,
  METERS_PER_SCENE_UNIT,
  projectBounds,
  ROAD_Y_OFFSET,
} from "@/lib/geo";
import {
  buildingHeightMeters,
  type CityData,
  usableRoads,
  utilityBuildingColors,
} from "@/lib/city";
import { validLocation } from "@/lib/utils";
import { useUtilityColor } from "../UtilityColors";
import type { Project } from "@/lib/types";

function BuildingsLayer({
  city,
  projects,
  visible,
}: {
  city: CityData;
  projects: Project[];
  visible: boolean;
}) {
  const utilityColor = useUtilityColor();
  const bounds = useMemo(() => projectBounds(projects), [projects]);
  const geometry = useMemo(() => {
    const associations = utilityBuildingColors(projects, city.buildings);
    const parts: THREE.ExtrudeGeometry[] = [];
    for (const building of city.buildings) {
      if (
        building.points.length < 3 ||
        !building.points.every(([lng, lat]) =>
          validLocation({ longitude: lng, latitude: lat }),
        )
      )
        continue;
      const footprint = building.points.map(([lng, lat]) =>
        clampScenePoint(geoToScene(lng, lat), bounds),
      );
      const shape = new THREE.Shape(
        footprint.map((p) => new THREE.Vector2(p.x, -p.z)),
      );
      const mesh = new THREE.ExtrudeGeometry(shape, {
        depth: buildingHeightMeters(building) / METERS_PER_SCENE_UNIT,
        bevelEnabled: false,
        curveSegments: 1,
      });
      mesh.rotateX(-Math.PI / 2);
      const utilityId = associations.get(building.id);
      const color = new THREE.Color(
        utilityId ? utilityColor(utilityId) : "#cfd8d4",
      );
      const colors = new Float32Array(mesh.getAttribute("position").count * 3);
      for (let i = 0; i < colors.length; i += 3) {
        colors[i] = color.r;
        colors[i + 1] = color.g;
        colors[i + 2] = color.b;
      }
      mesh.setAttribute("color", new THREE.BufferAttribute(colors, 3));
      parts.push(mesh);
    }
    const combined = parts.length ? mergeGeometries(parts, false) : null;
    parts.forEach((part) => part.dispose());
    return combined;
  }, [bounds, city, projects, utilityColor]);
  useEffect(() => () => geometry?.dispose(), [geometry]);
  if (!geometry) return null;
  return (
    <mesh geometry={geometry} frustumCulled={false} visible={visible}>
      <meshStandardMaterial
        vertexColors
        roughness={0.92}
        side={THREE.DoubleSide}
      />
    </mesh>
  );
}

function RoadsLayer({
  city,
  visible,
  bounds,
}: {
  city: CityData;
  visible: boolean;
  bounds: ReturnType<typeof projectBounds>;
}) {
  const geometry = useMemo(() => {
    const values: number[] = [];
    for (const road of usableRoads(city)) {
      for (let i = 0; i < road.points.length - 1; i++) {
        const a = clampScenePoint(
            geoToScene(...road.points[i], ROAD_Y_OFFSET),
            bounds,
          ),
          b = clampScenePoint(
            geoToScene(...road.points[i + 1], ROAD_Y_OFFSET),
            bounds,
          );
        values.push(a.x, a.y, a.z, b.x, b.y, b.z);
      }
    }
    const buffer = new THREE.BufferGeometry();
    buffer.setAttribute(
      "position",
      new THREE.Float32BufferAttribute(values, 3),
    );
    return buffer;
  }, [bounds, city]);
  useEffect(() => () => geometry.dispose(), [geometry]);
  return (
    <lineSegments geometry={geometry} frustumCulled={false} visible={visible}>
      <lineBasicMaterial color="#afb9b8" transparent opacity={0.8} />
    </lineSegments>
  );
}

export function CityModel({
  city,
  projects,
  roadsVisible,
  buildingsVisible,
}: {
  city: CityData | null;
  projects: Project[];
  roadsVisible: boolean;
  buildingsVisible: boolean;
}) {
  const bounds = useMemo(() => projectBounds(projects), [projects]);
  const ground = useMemo(() => {
    if (bounds) {
      const width = Math.max(bounds.maxX - bounds.minX, 90);
      const height = Math.max(bounds.maxZ - bounds.minZ, 90);
      return {
        x: (bounds.minX + bounds.maxX) / 2,
        z: (bounds.minZ + bounds.maxZ) / 2,
        width: width + 30,
        height: height + 30,
      };
    }
    const [west, south, east, north] = city?.bbox ?? [
      -80.219, 25.764, -80.19, 25.79,
    ];
    const a = geoToScene(west, south),
      b = geoToScene(east, north);
    return {
      x: (a.x + b.x) / 2,
      z: (a.z + b.z) / 2,
      width: Math.abs(b.x - a.x) + 80,
      height: Math.abs(b.z - a.z) + 80,
    };
  }, [bounds, city]);
  return (
    <group>
      <mesh rotation={[-Math.PI / 2, 0, 0]} position={[ground.x, 0, ground.z]}>
        <planeGeometry args={[ground.width, ground.height]} />
        <meshStandardMaterial color="#f4f6f4" roughness={1} />
      </mesh>
      {city && (
        <BuildingsLayer
          city={city}
          projects={projects}
          visible={buildingsVisible}
        />
      )}
      {city && bounds && <RoadsLayer city={city} visible={roadsVisible} bounds={bounds} />}
    </group>
  );
}
