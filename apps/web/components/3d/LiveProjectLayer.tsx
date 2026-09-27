"use client";
import { Html, Line, OrbitControls } from "@react-three/drei";
import { useThree } from "@react-three/fiber";
import { useEffect, useMemo, useRef, useState, type RefObject } from "react";
import type { OrbitControls as Controls } from "three-stdlib";
import type { Match, Project } from "@/lib/types";
import { projectDateStatus } from "@/lib/utils";
import { useUtilityColor } from "../UtilityColors";

/** Actual API Point/LineString geometry. No road snapping or invented buildings. */
export function LiveProjectLayer({
  projects,
  matches,
  selectedMatchId,
  onSelectMatch,
  labelPortal,
  resetSignal,
  conflictsVisible,
  selectedDate,
}: {
  projects: Project[];
  matches: Match[];
  selectedMatchId: string | null;
  onSelectMatch: (id: string | null) => void;
  labelPortal: RefObject<HTMLDivElement>;
  resetSignal: number;
  conflictsVisible: boolean;
  selectedDate: string | null;
}) {
  const color = useUtilityColor();
  const { camera } = useThree();
  const controls = useRef<Controls>(null);
  const [inspected, setInspected] = useState<string | null>(null);
  const items = useMemo(() => {
    const mapped = projects.flatMap((p) =>
      p.geometry
        ? [
            {
              project: p,
              coordinates:
                p.geometry.type === "Point"
                  ? [p.geometry.coordinates]
                  : p.geometry.coordinates,
            },
          ]
        : [],
    );
    const all = mapped.flatMap((p) => p.coordinates);
    if (!all.length) return [];
    const west = Math.min(...all.map((p) => p[0])),
      east = Math.max(...all.map((p) => p[0]));
    const south = Math.min(...all.map((p) => p[1])),
      north = Math.max(...all.map((p) => p[1]));
    const longitude = (west + east) / 2,
      latitude = (south + north) / 2;
    const longitudeScale = Math.cos((latitude * Math.PI) / 180);
    const scale =
      220 / Math.max((east - west) * longitudeScale, north - south, 0.006);
    return mapped.map((p) => ({
      ...p,
      points: p.coordinates.map(
        (c) =>
          [
            (c[0] - longitude) * longitudeScale * scale,
            0.5,
            -(c[1] - latitude) * scale,
          ] as [number, number, number],
      ),
    }));
  }, [projects]);
  useEffect(() => {
    camera.position.set(145, 220, 230);
    camera.lookAt(0, 0, 0);
    controls.current?.target.set(0, 0, 0);
    controls.current?.update();
  }, [camera, items, resetSignal]);
  const selected = matches.find((m) => m.id === selectedMatchId);
  const choose = (id: string) => {
    setInspected(id);
    const match = matches.find((m) => m.projectIds.includes(id));
    if (match) onSelectMatch(match.id);
  };
  return (
    <>
      <OrbitControls
        ref={controls}
        enableDamping
        minDistance={12}
        maxDistance={1800}
        maxPolarAngle={Math.PI / 2.1}
      />
      <gridHelper args={[360, 18, "#c4cbd3", "#dce1e6"]} />
      {items.map(({ project: p, points }) => {
        const focused =
          selected?.projectIds.includes(p.id) || inspected === p.id;
        const status = projectDateStatus(p, selectedDate);
        const opacity = focused || status === "active" ? 1 : status === "unknown" ? 0.8 : 0.5;
        return (
          <group key={p.id}>
            {points.length > 1 ? (
              <Line
                points={points}
                color={color(p.utilityId)}
                lineWidth={focused ? 7 : 4}
                transparent
                opacity={opacity}
                onClick={(e) => {
                  e.stopPropagation();
                  choose(p.id);
                }}
              />
            ) : (
              <mesh
                position={points[0]}
                onClick={(e) => {
                  e.stopPropagation();
                  choose(p.id);
                }}
              >
                <sphereGeometry args={[focused ? 2.5 : 1.7, 16, 12]} />
                <meshBasicMaterial color={color(p.utilityId)} transparent opacity={opacity} />
              </mesh>
            )}
            {focused && (
              <Html
                portal={labelPortal}
                position={points[Math.floor(points.length / 2)]}
                center
                zIndexRange={[19, 0]}
              >
                <button
                  className="map-project-label"
                  style={{ borderColor: color(p.utilityId) }}
                  onClick={() => choose(p.id)}
                >
                  {p.name}
                  <small>Construction: {status}</small>
                  <small>
                    {p.geometryQuality} · {p.validationState}
                  </small>
                </button>
              </Html>
            )}
          </group>
        );
      })}
      {matches
        .filter((m) => m.id === selectedMatchId || conflictsVisible)
        .map((m) => {
          const pair = m.projectIds.map((id) =>
            items.find((p) => p.project.id === id),
          );
          if (!pair[0] || !pair[1]) return null;
          const a = pair[0].points[0],
            b = pair[1].points[0];
          const focused = m.id === selectedMatchId;
          return (
            <group key={m.id}>
              <Line
                points={[a, b]}
                color={focused ? "#a21caf" : "#b8a0bf"}
                lineWidth={focused ? 3 : 1}
                dashed
                dashSize={2}
                gapSize={1}
                onClick={(e) => {
                  e.stopPropagation();
                  onSelectMatch(m.id);
                }}
              />
              {focused && (
                <Html
                  portal={labelPortal}
                  position={[(a[0] + b[0]) / 2, 5, (a[2] + b[2]) / 2]}
                  center
                  zIndexRange={[20, 0]}
                >
                  <button
                    className="map-distance"
                    onClick={() => onSelectMatch(m.id)}
                  >
                    {m.distanceMiles.toFixed(2)} mi · {m.tier}
                    <small className="block">
                      Pair link, not a measured route
                    </small>
                  </button>
                </Html>
              )}
            </group>
          );
        })}
    </>
  );
}
