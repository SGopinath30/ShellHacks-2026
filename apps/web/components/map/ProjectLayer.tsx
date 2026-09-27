import { Marker, type Map } from "maplibre-gl";
import type { Project } from "@/lib/types";
import { utilityColor, validLocation } from "@/lib/utils";
export function addProjectMarkers(
  map: Map,
  projects: Project[],
  onSelect: (id: string) => void,
) {
  const markers = new globalThis.Map<string, Marker>();
  for (const project of projects) {
    if (!validLocation(project.location)) continue;
    const button = document.createElement("button");
    button.className = "map-marker";
    button.style.background = utilityColor(project.utilityId);
    button.textContent = project.id.slice(1);
    button.setAttribute(
      "aria-label",
      `Select ${project.name}, ${project.utilityName}`,
    );
    button.title = `${project.name}${project.synthetic ? " · Synthetic" : ""}`;
    button.onclick = () => onSelect(project.id);
    markers.set(
      project.id,
      new Marker({ element: button })
        .setLngLat([project.location.longitude, project.location.latitude])
        .addTo(map),
    );
  }
  return markers;
}
