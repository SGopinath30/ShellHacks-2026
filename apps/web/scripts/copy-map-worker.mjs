import { copyFileSync, mkdirSync } from "node:fs";
import { fileURLToPath } from "node:url";
// MapLibre's worker imports its shared sibling; Next must serve both together.
const target = new URL("../public/maplibre/", import.meta.url);
mkdirSync(target, { recursive: true });
for (const name of ["maplibre-gl-worker.mjs", "maplibre-gl-shared.mjs"]) {
  copyFileSync(
    fileURLToPath(
      new URL(`../node_modules/maplibre-gl/dist/${name}`, import.meta.url),
    ),
    fileURLToPath(new URL(name, target)),
  );
}
