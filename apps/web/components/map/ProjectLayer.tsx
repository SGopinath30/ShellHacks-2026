import { Marker, type Map } from "maplibre-gl";
import type { Project } from "@/lib/types";
import { utilityColor } from "@/lib/utils";
export function addProjectMarkers(
  map: Map,
  projects: Project[],
  selectedIds: string[],
  onSelect: (id: string) => void,
) {
  const markers = projects.map((project) => {
    const el = document.createElement("button");
    el.className = `map-marker ${selectedIds.includes(project.id) ? "active" : ""}`;
    el.style.background = utilityColor(project.utilityId);
    el.textContent = project.id.slice(1);
    el.setAttribute(
      "aria-label",
      `Select ${project.name}, ${project.utilityName}`,
    );
    el.title = `${project.name} · Synthetic`;
    el.onclick = () => onSelect(project.id);
    return new Marker({ element: el })
      .setLngLat([project.location.longitude, project.location.latitude])
      .addTo(map);
  });
  return () => markers.forEach((marker) => marker.remove());
}
