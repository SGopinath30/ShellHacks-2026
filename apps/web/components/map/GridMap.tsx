"use client";
import { useEffect, useRef, useState } from "react";
import {
  Map,
  NavigationControl,
  LngLatBounds,
  setWorkerUrl,
} from "maplibre-gl";
import type { Project } from "@/lib/types";
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
  const [ready, setReady] = useState(false);
  const [error, setError] = useState(false);
  useEffect(() => {
    if (!container.current) return;
    let map: Map;
    try {
      setWorkerUrl("/maplibre/maplibre-gl-worker.mjs");
      map = new Map({
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
      };
    } catch {
      setTimeout(() => setError(true), 0);
    }
  }, []);
  useEffect(() => {
    const map = mapRef.current;
    if (!ready || !map) return;
    const cleanup = addProjectMarkers(map, projects, selectedIds, onSelect);
    const selected = projects.filter((p) => selectedIds.includes(p.id));
    updateConnector(map, selected);
    const bounds = new LngLatBounds();
    (selected.length ? selected : projects).forEach((p) =>
      bounds.extend([p.location.longitude, p.location.latitude]),
    );
    map.fitBounds(bounds, {
      padding: 85,
      maxZoom: 14,
      duration: window.matchMedia("(prefers-reduced-motion: reduce)").matches
        ? 0
        : 700,
    });
    return cleanup;
  }, [projects, selectedIds, onSelect, ready]);
  return (
    <div className="map-shell">
      <div
        ref={container}
        className="map-canvas"
        role="region"
        aria-label="Interactive map of synthetic Miami utility projects"
      />
      <div className="map-location">
        <span className="live-dot" /> Miami, Florida{" "}
        <span>Demo study area</span>
      </div>
      {error && (
        <div className="map-error" role="status">
          Some map content could not load. Check your connection or WebGL
          support. Project cards, schedules, and evidence remain available.
        </div>
      )}
      <div className="map-caption">
        Dashed line: proximity connector · Not a verified corridor
      </div>
    </div>
  );
}
