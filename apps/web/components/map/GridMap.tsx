"use client";
import { useEffect, useRef, useState } from "react";
import {
  Map,
  Marker,
  NavigationControl,
  LngLatBounds,
  setWorkerUrl,
} from "maplibre-gl";
import type { Project } from "@/lib/types";
import { validLocation } from "@/lib/utils";
import { addProjectMarkers } from "./ProjectLayer";
import { updateConnector } from "./MatchConnector";
export default function GridMap({
  projects,
  selectedIds,
  onSelect,
}: {
  projects: Project[];
  selectedIds: string[];
  onSelect: (id: string) => void;
}) {
  const container = useRef<HTMLDivElement>(null);
  const mapRef = useRef<Map | null>(null);
  const markersRef = useRef<globalThis.Map<string, Marker>>(
    new globalThis.Map(),
  );
  const selectRef = useRef(onSelect);
  useEffect(() => { selectRef.current = onSelect; }, [onSelect]);
  const fitKeyRef = useRef<string | null>(null);
  const [ready, setReady] = useState(false);
  const [error, setError] = useState(false);
  const validProjects = projects.filter((p) => validLocation(p.location));
  const unavailableCount = projects.length - validProjects.length;
  const selected = selectedIds
    .map((id) => projects.find((p) => p.id === id))
    .filter((p): p is Project => Boolean(p));
  const selectedValid = selected.filter((p) => validLocation(p.location));
  const selectedKey = selectedIds
    .map((id) => {
      const p = projects.find((p) => p.id === id);
      return p && validLocation(p.location)
        ? `${id}:${p.location.longitude},${p.location.latitude}`
        : `${id}:unavailable`;
    })
    .join("|");
  const allKey = validProjects
    .map((p) => `${p.id}:${p.location!.longitude},${p.location!.latitude}`)
    .join("|");
  useEffect(() => {
    if (!container.current) return;
    try {
      setWorkerUrl("/maplibre/maplibre-gl-worker.mjs");
      const map = new Map({
        container: container.current,
        center: [-80.205, 25.786],
        zoom: 12,
        style: {
          version: 8,
          sources: {
            osm: {
              type: "raster",
              tiles: ["https://tile.openstreetmap.org/{z}/{x}/{y}.png"],
              tileSize: 256,
              attribution:
                '© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
              maxzoom: 19,
            },
          },
          layers: [
            {
              id: "basemap",
              type: "raster",
              source: "osm",
              paint: { "raster-saturation": -0.85, "raster-opacity": 0.75 },
            },
          ],
        },
      });
      mapRef.current = map;
      map.addControl(
        new NavigationControl({ showCompass: false }),
        "top-right",
      );
      map.on("load", () => setReady(true));
      map.on("error", (event) => {
        console.warn("Map content error:", event.error.message);
        setError(true);
      });
      const observer = new ResizeObserver(() => map.resize());
      observer.observe(container.current);
      return () => {
        observer.disconnect();
        map.remove();
        mapRef.current = null;
        fitKeyRef.current = null;
      };
    } catch {
      setTimeout(() => setError(true), 0);
    }
  }, []);
  useEffect(() => {
    const map = mapRef.current;
    if (!ready || !map) return;
    const markers = addProjectMarkers(map, projects, (id) =>
      selectRef.current(id),
    );
    markersRef.current = markers;
    return () => {
      markers.forEach((marker) => marker.remove());
      markersRef.current = new globalThis.Map();
    };
  }, [ready, projects]);
  useEffect(() => {
    const map = mapRef.current;
    if (!ready || !map) return;
    markersRef.current.forEach((marker, id) =>
      marker.getElement().classList.toggle("active", selectedIds.includes(id)),
    );
    updateConnector(map, selectedIds.length === 2 ? selected : []);
    const frame =
      selectedIds.length === 2 && selectedValid.length === 2
        ? selectedValid
        : validProjects;
    const key = selectedIds.length === 2 ? selectedKey : `all:${allKey}`;
    if (fitKeyRef.current === key || !frame.length) return;
    fitKeyRef.current = key;
    const bounds = new LngLatBounds();
    frame.forEach((p) => {
      if (validLocation(p.location))
        bounds.extend([p.location.longitude, p.location.latitude]);
    });
    map.fitBounds(bounds, {
      padding: 85,
      maxZoom: 14,
      duration: window.matchMedia("(prefers-reduced-motion: reduce)").matches
        ? 0
        : 700,
    });
  }, [
    ready,
    projects,
    selectedKey,
    allKey,
    selectedIds,
    selected,
    selectedValid,
    validProjects,
  ]);
  return (
    <div className="map-shell">
      <div
        ref={container}
        className="map-canvas"
        role="region"
        aria-label="Interactive map of project locations"
      />
      <div className="map-location">
        <span className="live-dot" />
        Miami, Florida <span>Demo study area</span>
      </div>
      {error && (
        <div className="map-error" role="status">
          Some map content could not load. Check your connection or WebGL
          support. Project cards, schedules, and evidence remain available.
        </div>
      )}
      {!validProjects.length && (
        <div className="map-error" role="status">
          No project locations available.
        </div>
      )}
      {unavailableCount > 0 && validProjects.length > 0 && (
        <div className="map-error" role="status">
          {unavailableCount}{" "}
          {unavailableCount === 1 ? "project cannot" : "projects cannot"} be
          mapped because location data is missing or invalid.
        </div>
      )}
      {selectedIds.length === 2 && selectedValid.length !== 2 && (
        <div className="map-error" role="status">
          The selected pair cannot be mapped completely because location data is
          incomplete.
        </div>
      )}
      <div className="map-caption">
        Dashed line: proximity connector · Not a verified corridor
      </div>
    </div>
  );
}
