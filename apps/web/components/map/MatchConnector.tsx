import type { GeoJSONSource, Map } from "maplibre-gl";
import type { FeatureCollection } from "geojson";
import type { Project } from "@/lib/types";
export function updateConnector(map: Map, projects: Project[]) {
  const data: FeatureCollection = {
    type: "FeatureCollection",
    features:
      projects.length === 2
        ? [
            {
              type: "Feature",
              properties: {},
              geometry: {
                type: "LineString",
                coordinates: projects.map((p) => [
                  p.location.longitude,
                  p.location.latitude,
                ]),
              },
            },
          ]
        : [],
  };
  const source = map.getSource("proximity") as GeoJSONSource | undefined;
  if (source) source.setData(data);
  else {
    map.addSource("proximity", { type: "geojson", data });
    map.addLayer({
      id: "proximity-line",
      type: "line",
      source: "proximity",
      paint: {
        "line-color": "#26766c",
        "line-width": 3,
        "line-dasharray": [2, 2],
      },
    });
  }
}
