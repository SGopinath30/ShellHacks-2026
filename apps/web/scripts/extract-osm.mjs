// Optional asset refresh: download an OSM API 0.6 XML extract, then run this
// script with the XML path. Never synthesizes buildings or streets.
import { readFileSync, writeFileSync } from "node:fs";
const attribute = (tag, key) =>
  tag.match(new RegExp(`\\b${key}="([^"]*)"`))?.[1] ?? null;
const buildings = new Map(),
  roads = new Map();
let bbox = null;
for (const file of process.argv.slice(2)) {
  const input = readFileSync(file, "utf8");
  if (file.endsWith(".json")) {
    const data = JSON.parse(input);
    for (const item of data.buildings) buildings.set(item.id, item);
    for (const item of data.roads) roads.set(item.id, item);
    bbox = data.bbox;
    continue;
  }
  const xml = input;
  const bounds = xml.match(/<bounds\s[^>]*\/>/)?.[0];
  if (bounds) {
    const next = [
      Number(attribute(bounds, "minlon")),
      Number(attribute(bounds, "minlat")),
      Number(attribute(bounds, "maxlon")),
      Number(attribute(bounds, "maxlat")),
    ];
    bbox = bbox
      ? [
          Math.min(bbox[0], next[0]),
          Math.min(bbox[1], next[1]),
          Math.max(bbox[2], next[2]),
          Math.max(bbox[3], next[3]),
        ]
      : next;
  }
  const nodes = new Map();
  for (const tag of xml.matchAll(/<node\s[^>]*\/>/g)) {
    const id = attribute(tag[0], "id");
    const lat = Number(attribute(tag[0], "lat"));
    const lng = Number(attribute(tag[0], "lon"));
    if (id && Number.isFinite(lat) && Number.isFinite(lng))
      nodes.set(id, [lng, lat]);
  }
  for (const way of xml.matchAll(/<way\s[^>]*>([\s\S]*?)<\/way>/g)) {
    const id = attribute(way[0].slice(0, way[0].indexOf(">") + 1), "id");
    const body = way[1];
    const points = [...body.matchAll(/<nd\s[^>]*\/>/g)]
      .map((match) => nodes.get(attribute(match[0], "ref")))
      .filter(Boolean);
    if (!id || points.length < 2) continue;
    const tags = new Map(
      [...body.matchAll(/<tag\s[^>]*\/>/g)].map((match) => [
        attribute(match[0], "k"),
        attribute(match[0], "v"),
      ]),
    );
    if (tags.has("building") && points.length >= 3)
      buildings.set(id, {
        id,
        points,
        height: tags.get("height") ?? null,
        levels: tags.get("building:levels") ?? null,
      });
    if (tags.has("highway"))
      roads.set(id, { id, points, kind: tags.get("highway") });
  }
}
const output = {
  source: "OpenStreetMap contributors",
  bbox,
  buildings: [...buildings.values()],
  roads: [...roads.values()],
};
writeFileSync("public/city-osm.json", JSON.stringify(output));
console.log(
  `Extracted ${buildings.size} buildings, ${roads.size} roads (${Buffer.byteLength(JSON.stringify(output))} bytes).`,
);
