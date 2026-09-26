# Synchro frontend

Next.js App Router, TypeScript, Tailwind CSS, and MapLibre. All utilities, project records, and evidence are fictional. The real Miami basemap supplies geographic context only.

From the repository root:

```powershell
npm --prefix apps/web install
npm --prefix apps/web run dev
```

Open http://localhost:3000. Node.js 20.9 or newer is required; development was performed with Node 24 and npm 11.

```powershell
npm --prefix apps/web run lint
npm --prefix apps/web run typecheck
npm --prefix apps/web test
npm --prefix apps/web run build
npm --prefix apps/web run test:browser
npm --prefix apps/web start
```

## Provisional data boundary

Browser checks use an installed Google Chrome, start a production server, and require a completed build. They cover desktop/mobile layout, selection and filters, evidence, unknown schedules, live map tiles, and simulated tile failure. Screenshots are written to the ignored `test-results/` directory.

The browser server uses port 3100 (override with `PLAYWRIGHT_PORT`) so it can run alongside the development server. Date edge cases render the actual details, card, and timeline components with test-only records into browser-checked markup; the existing dashboard tests exercise live interactions. Generated case markup is ignored in `.test-fixtures/`.

Construction windows are centrally classified as valid, incomplete, or invalid. Strict UTC calendar parsing rejects impossible dates and non-day formats. Only valid windows contribute to overlap, bars, and the timeline scale. Partial schedules retain known endpoints; invalid schedules retain supplied values for review. Demo filtering and rendering recalculate overlap from project records rather than trusting cached match values. Missing project references display an unavailable-data state. In-service milestones remain independent of construction timing.

`lib/types.ts` defines frontend-only contracts. `lib/api.ts` is a synchronous fixture adapter, not an established backend API. Replace this adapter when shared contracts and endpoints exist; real request errors must be surfaced, not silently replaced with fixtures.

Project locations are approximate WGS84 points. Dates are ISO calendar dates, evaluated in UTC. Construction intervals are start-inclusive and end-exclusive; missing endpoints produce null overlap. In-service dates are milestones only. All fixture precision is day or unknown. Evidence URLs are null because no actual source exists.

`lib/utils.ts` isolates haversine point distance and demo matching. Opportunities require different utilities, distance within the inclusive threshold, and positive overlap meeting the inclusive minimum. Unknown schedules are independently listed using only the distance threshold. Same-utility pairs and non-overlapping schedules never become opportunities. All projects remain visible on the map for context; clicking a marker selects its first currently visible pair if one exists.

## Map and limitations

Development and build scripts copy MapLibre's worker and its shared module from the installed dependency into an ignored public directory. This follows the [MapLibre Next.js setup](https://maplibre.org/maplibre-gl-js/docs/) and keeps the worker version aligned with the library.

The map uses public OpenStreetMap raster tiles without a key, with attribution. Internet access and WebGL are required for the basemap. Tile or WebGL errors leave cards, filters, details, evidence, and timelines usable. Follow the [OSM tile usage policy](https://operations.osmfoundation.org/policies/tiles/) and select an appropriate provider before production traffic. The dashed connector indicates proximity, not an engineering corridor. No backend, ingestion, authentication, or engineering feasibility analysis is implemented.

The scaffold follows [Next.js manual installation](https://nextjs.org/docs/app/getting-started/installation), [Tailwind PostCSS setup](https://tailwindcss.com/docs/installation/using-postcss), and the [MapLibre Map API](https://maplibre.org/maplibre-gl-js/docs/API/classes/Map/).
