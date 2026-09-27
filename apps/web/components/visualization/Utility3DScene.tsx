"use client";
import { Canvas } from "@react-three/fiber";
import {
  Component,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import type { Match, Project } from "@/lib/types";
import type { CityData } from "@/lib/city";
import { parseCityData } from "@/lib/city";
import { formatDate, utilityLegend, resolvePair } from "@/lib/utils";
import { CityModel } from "@/components/3d/CityModel";
import { SceneCamera } from "@/components/3d/SceneCamera";
import { UtilityLayer } from "@/components/3d/UtilityLayer";
import { LiveProjectLayer } from "@/components/3d/LiveProjectLayer";
import { useUtilityColor } from "../UtilityColors";

class SceneBoundary extends Component<
  { children: ReactNode },
  { failed: boolean }
> {
  state = { failed: false };
  static getDerivedStateFromError() {
    return { failed: true };
  }
  render() {
    return this.state.failed ? (
      <div className="scene-unavailable">
        The 3D view is unavailable. Project details and schedules remain
        accessible.
      </div>
    ) : (
      this.props.children
    );
  }
}

export default function Utility3DScene({
  projects,
  matches,
  selectedDate,
  selectedMatchId,
  onSelectMatch,
  live = false,
}: {
  projects: Project[];
  matches: Match[];
  selectedDate: string | null;
  selectedMatchId: string | null;
  onSelectMatch: (id: string | null) => void;
  live?: boolean;
}) {
  const [city, setCity] = useState<CityData | null>(null);
  const color = useUtilityColor();
  const [cityError, setCityError] = useState(false);
  // The host mounts before Canvas creates its scene; Drei expects a non-null ref type.
  const labelPortal = useRef<HTMLDivElement>(null!);
  const [resetSignal, setResetSignal] = useState(0);
  const [roadsVisible, setRoadsVisible] = useState(true);
  const [buildingsVisible, setBuildingsVisible] = useState(true);
  const [conflictsVisible, setConflictsVisible] = useState(true);
  const legend = useMemo(() => utilityLegend(projects), [projects]);
  const selectedPair = useMemo(() => {
    const match = matches.find((m) => m.id === selectedMatchId);
    return match ? resolvePair(match, projects) : null;
  }, [matches, projects, selectedMatchId]);
  useEffect(() => {
    if (live) return;
    const controller = new AbortController();
    fetch("/city-osm.json", { signal: controller.signal })
      .then((response) => {
        if (!response.ok) throw new Error("City data unavailable");
        return response.json();
      })
      .then((payload) => setCity(parseCityData(payload)))
      .catch((error) => {
        if (!controller.signal.aborted) {
          console.warn("OSM city data could not load", error);
          setCityError(true);
        }
      });
    return () => controller.abort();
  }, [live]);
  return (
    <div className="scene-shell">
      <div className="scene-header">
        <h2>3D utility coordination</h2>
        <span className="mini-badge">
          {selectedDate ? formatDate(selectedDate) : "No selected date"}
        </span>
      </div>
      <div className="scene-viewport">
        <div ref={labelPortal} className="scene-label-layer" />
        <SceneBoundary>
          <Canvas
            camera={{
              position: [160, 220, 210],
              fov: 42,
              near: 0.1,
              far: 5000,
            }}
            onPointerMissed={() => {
              onSelectMatch(null);
            }}
            gl={{ antialias: true }}
          >
            <color attach="background" args={["#edf1f1"]} />
            <ambientLight intensity={0.8} />
            <hemisphereLight args={["#ffffff", "#c8d1d0", 0.55]} />
            <directionalLight position={[100, 180, 80]} intensity={1.25} />
            {live ? (
              <LiveProjectLayer
                selectedDate={selectedDate}
                projects={projects}
                matches={matches}
                selectedMatchId={selectedMatchId}
                onSelectMatch={onSelectMatch}
                labelPortal={labelPortal}
                resetSignal={resetSignal}
                conflictsVisible={conflictsVisible}
              />
            ) : (
              <>
                <CityModel
                  city={city}
                  projects={projects}
                  roadsVisible={roadsVisible}
                  buildingsVisible={buildingsVisible}
                />
                <UtilityLayer
                  projects={projects}
                  matches={matches}
                  city={city}
                  selectedDate={selectedDate}
                  selectedMatchId={selectedMatchId}
                  onSelectMatch={onSelectMatch}
                  labelPortal={labelPortal}
                  conflictsVisible={conflictsVisible}
                />
                <SceneCamera
                  projects={selectedPair ?? projects}
                  resetSignal={resetSignal}
                />
              </>
            )}
          </Canvas>
        </SceneBoundary>
        <div className="scene-view-controls">
          <button
            type="button"
            onClick={() => setResetSignal((value) => value + 1)}
          >
            Reset View
          </button>
          <button
            type="button"
            disabled={live}
            title={
              live
                ? "Building footprints are not supplied by the API"
                : undefined
            }
            onClick={() => setBuildingsVisible((value) => !value)}
          >
            {live
              ? "Buildings: unavailable"
              : buildingsVisible
                ? "Buildings: on"
                : "Buildings: off"}
          </button>
          <button
            type="button"
            disabled={live}
            title={
              live ? "Road geometry is not supplied by the API" : undefined
            }
            onClick={() => setRoadsVisible((value) => !value)}
          >
            {live
              ? "Roads: unavailable"
              : roadsVisible
                ? "Roads: on"
                : "Roads: off"}
          </button>
          <button
            type="button"
            onClick={() => setConflictsVisible((value) => !value)}
          >
            {conflictsVisible ? "Conflicts: on" : "Conflicts: off"}
          </button>
        </div>
        <div className="scene-legend-overlay">
          {legend.map((item) => (
            <span key={item.id} className="scene-legend-item">
              <i
                className="scene-legend-swatch"
                style={{ background: color(item.id) }}
              />
              {item.name}
            </span>
          ))}
          <span className="scene-legend-item">
            <i className="scene-legend-swatch scene-legend-swatch-danger" />
            {live ? "API opportunity link" : "Collision / Synergy Alert"}
          </span>
        </div>
        <div className="scene-attribution">
          {live ? (
            "API project geometry · Dashed links show pairs, not routes or verified shared infrastructure"
          ) : (
            <>
              <a
                href="https://www.openstreetmap.org/copyright"
                target="_blank"
                rel="noopener noreferrer"
              >
                © OpenStreetMap contributors
              </a>{" "}
              · Utility paths and colored building associations are illustrative
            </>
          )}
        </div>
        {cityError && (
          <div className="scene-data-notice" role="status">
            City geometry could not load; project and timeline data remain
            available.
          </div>
        )}
        {!live && !city && !cityError && (
          <div className="scene-data-notice" role="status">
            Loading OpenStreetMap city geometry…
          </div>
        )}
        {live && !projects.some((p) => p.geometry) && (
          <div className="scene-data-notice" role="status">
            No mapped project geometry available.
          </div>
        )}
      </div>
    </div>
  );
}
