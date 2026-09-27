"use client";
import { Html, Line } from "@react-three/drei";
import { useMemo, useState, type RefObject } from "react";
import * as THREE from "three";
import { utilityPaths, type CityData, type UtilityPath } from "@/lib/city";
import {
  clampScenePoint,
  geoToScene,
  CONFLICT_Y_OFFSET,
  projectBounds,
} from "@/lib/geo";
import type { Match, Project, CoordinationMatch } from "@/lib/types";
import { projectDateStatus, validLocation } from "@/lib/utils";
import {
  coordinationMatch,
  relationshipPhase,
  timingLabel,
} from "@/lib/coordination";
import { useUtilityColor } from "../UtilityColors";

function UtilityLine({
  path,
  selectedDate,
  selected,
  dimmed,
  onSelect,
  labelPortal,
}: {
  path: UtilityPath;
  selectedDate: string | null;
  selected: boolean;
  dimmed: boolean;
  onSelect: () => void;
  labelPortal: RefObject<HTMLDivElement>;
}) {
  const color = useUtilityColor();
  const [hovered, setHovered] = useState(false);
  const status = projectDateStatus(path.project, selectedDate);
  const points = useMemo(
    () => path.points.map((p) => new THREE.Vector3(p.x, p.y, p.z)),
    [path.points],
  );
  return (
    <group>
      <Line
        points={points}
        color={color(path.project.utilityId)}
        lineWidth={selected ? 9 : hovered ? 7 : 5}
        transparent
        opacity={
          dimmed
            ? 0.15
            : status === "active"
              ? 1
              : selected
                ? 0.65
                : status === "planned"
                  ? 0.35
                  : 0.22
        }
        onClick={(e) => {
          e.stopPropagation();
          onSelect();
        }}
        onPointerOver={(e) => {
          e.stopPropagation();
          setHovered(true);
        }}
        onPointerOut={() => setHovered(false)}
      />
      {hovered && (
        <Html
          portal={labelPortal}
          position={points[Math.floor(points.length / 2)]}
          center
        >
          <div className="scene-tooltip">
            <strong>{path.project.name}</strong>
            <div>{status} · Illustrative road alignment</div>
          </div>
        </Html>
      )}
    </group>
  );
}
function Relationship({
  match,
  active,
  selected,
  onSelect,
  labelPortal,
  sceneBounds,
}: {
  match: CoordinationMatch;
  active: boolean;
  selected: boolean;
  onSelect: () => void;
  labelPortal: RefObject<HTMLDivElement>;
  sceneBounds: ReturnType<typeof projectBounds>;
}) {
  if (!match.closestPoints) return null;
  const positions = match.closestPoints.map((point) =>
    clampScenePoint(
      geoToScene(point.longitude, point.latitude, CONFLICT_Y_OFFSET),
      sceneBounds,
    ),
  );
  const [a, b] = positions;
  const center: [number, number, number] = [
    (a.x + b.x) / 2,
    CONFLICT_Y_OFFSET,
    (a.z + b.z) / 2,
  ];
  return (
    <group>
      {selected && (
        <>
          <Line
            points={positions.map((p) => new THREE.Vector3(p.x, p.y, p.z))}
            color="#bd492d"
            lineWidth={3}
            dashed
            dashSize={2}
            gapSize={1}
            depthTest={false}
            depthWrite={false}
            renderOrder={10}
          />
          {positions.map((p, i) => (
            <mesh
              key={i}
              position={[p.x, p.y, p.z]}
              rotation={[-Math.PI / 2, 0, 0]}
              renderOrder={11}
            >
              <ringGeometry args={[1.3, 2, 32]} />
              <meshBasicMaterial
                color="#d59124"
                depthTest={false}
                depthWrite={false}
                side={THREE.DoubleSide}
              />
            </mesh>
          ))}
          <Html
            portal={labelPortal}
            position={[center[0], center[1] + 3, center[2]]}
            center
            zIndexRange={[20, 0]}
          >
            <div className="map-distance">
              {match.distanceMiles.toFixed(2)} mi · source points
            </div>
          </Html>
        </>
      )}
      {(active || (selected && match.eligible)) && (
        <>
          <mesh
            position={center}
            rotation={[-Math.PI / 2, 0, 0]}
            renderOrder={12}
          >
            <ringGeometry args={[3.2, 3.6, 40]} />
            <meshBasicMaterial
              color="#d99a22"
              transparent
              opacity={active ? 0.85 : 0.35}
              depthTest={false}
              depthWrite={false}
              side={THREE.DoubleSide}
            />
          </mesh>
          <Html
            portal={labelPortal}
            position={center}
            center
            zIndexRange={[21, 0]}
          >
            <button
              className={`map-alert ${active ? "pulsing-alert" : ""}`}
              onClick={(e) => {
                e.stopPropagation();
                onSelect();
              }}
              aria-label={`${active ? "Collision / Synergy Alert" : "Coordination opportunity"}: ${match.distanceMiles.toFixed(2)} miles, ${timingLabel(match)}`}
              title={`${active ? "Collision / Synergy Alert" : "Coordination opportunity"} — open dossier`}
            >
              !
            </button>
          </Html>
        </>
      )}
    </group>
  );
}

export function UtilityLayer({
  projects,
  matches,
  city,
  selectedDate,
  selectedMatchId,
  onSelectMatch,
  labelPortal,
  conflictsVisible,
}: {
  projects: Project[];
  matches: Match[];
  city: CityData | null;
  selectedDate: string | null;
  selectedMatchId: string | null;
  onSelectMatch: (id: string | null) => void;
  labelPortal: RefObject<HTMLDivElement>;
  conflictsVisible: boolean;
}) {
  const color = useUtilityColor();
  const sceneBounds = useMemo(() => projectBounds(projects), [projects]);
  const paths = useMemo(
    () => (city ? utilityPaths(projects, city.roads) : []),
    [projects, city],
  );
  const [inspectedProjectId, setInspectedProjectId] = useState<string | null>(
    null,
  );
  const relationships = useMemo(
    () =>
      matches.flatMap((m) => {
        const result = coordinationMatch(m, projects);
        return result ? [result] : [];
      }),
    [matches, projects],
  );
  const selected = relationships.find((m) => m.id === selectedMatchId);
  const pairIds = new Set(selected?.projectIds ?? []);
  const chooseProject = (id: string) => {
    const match =
      relationships.find((m) => m.eligible && m.projectIds.includes(id)) ??
      relationships.find((m) => m.projectIds.includes(id));
    if (match) {
      setInspectedProjectId(null);
      onSelectMatch(match.id);
    } else setInspectedProjectId((current) => (current === id ? null : id));
  };
  return (
    <group>
      {paths.map((path) => (
        <UtilityLine
          key={path.project.id}
          path={path}
          selectedDate={selectedDate}
          selected={pairIds.has(path.project.id)}
          dimmed={!!selected && !pairIds.has(path.project.id)}
          onSelect={() => chooseProject(path.project.id)}
          labelPortal={labelPortal}
        />
      ))}
      {projects
        .filter((p) => validLocation(p.location))
        .map((p) => {
          const position = clampScenePoint(
            geoToScene(
              p.location!.longitude,
              p.location!.latitude,
              CONFLICT_Y_OFFSET,
            ),
            sceneBounds,
          );
          const active = projectDateStatus(p, selectedDate) === "active";
          return (
            <group key={p.id}>
              <mesh
                position={[position.x, position.y, position.z]}
                onClick={(e) => {
                  e.stopPropagation();
                  chooseProject(p.id);
                }}
              >
                <sphereGeometry
                  args={[pairIds.has(p.id) ? 1.3 : 0.9, 12, 10]}
                />
                <meshBasicMaterial
                  color={color(p.utilityId)}
                  transparent
                  opacity={active || pairIds.has(p.id) ? 1 : 0.4}
                  depthTest={false}
                />
              </mesh>
              {(pairIds.has(p.id) || inspectedProjectId === p.id) && (
                <Html
                  portal={labelPortal}
                  position={[position.x, position.y + 3, position.z]}
                  center
                  zIndexRange={[19, 0]}
                >
                  <button
                    className="map-project-label"
                    style={{ borderColor: color(p.utilityId) }}
                    onClick={() => chooseProject(p.id)}
                  >
                    {p.name}
                    <small>{projectDateStatus(p, selectedDate)}</small>
                    {inspectedProjectId === p.id && (
                      <small>No opportunity within current filters</small>
                    )}
                  </button>
                </Html>
              )}
            </group>
          );
        })}
      {relationships
        .filter(
          (m) =>
            m.id === selectedMatchId ||
            (conflictsVisible &&
              m.eligible &&
              relationshipPhase(m, selectedDate) === "active"),
        )
        .map((match) => (
          <Relationship
            key={match.id}
            match={match}
            selected={match.id === selectedMatchId}
            active={
              conflictsVisible &&
              relationshipPhase(match, selectedDate) === "active"
            }
            labelPortal={labelPortal}
            sceneBounds={sceneBounds}
            onSelect={() => onSelectMatch(match.id)}
          />
        ))}
    </group>
  );
}
