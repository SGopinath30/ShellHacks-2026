# Synchro

Turns fragmented utility construction plans into an explainable geospatial timeline, using AI for document extraction and deterministic spatial and schedule matching to surface cross-utility coordination opportunities.

Backend work is organized by owner:

- `Tarun/` — project intelligence, evidence validation, extraction, and Nemotron integration.
- `gridlock-control-plane/` — Kevin's deterministic opportunity and control-plane service.
- `ingestion/` — Dell's source ingestion and unverified candidate handoff.

## Dell ingestion v0

Dell preserves public evidence and discovers **unverified** geometry candidates. Mac validates project associations; ASUS calculates overlap. The Dell ingestion package contains no AI extraction, overlap engine, or frontend.

### Run the offline demo

Python 3.11+ is required. In PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m ingestion --data-dir data/demo demo
.\.venv\Scripts\python.exe -m pytest -q
```

The demo creates **two invented projects**, one endpoint segment, one point, and one invented overlap fixture row. It is not the organizer workbook or a claim about real projects. Rerunning detects the same source bytes and reuses the parsed artifact.

The command prints an output directory containing:

- `starter_projects.json`: mapped values, original cells, source IDs, sheet/row locators.
- `starter_overlaps.json`: original fixture claims, never calculated overlap results.
- `geometry_candidates.json`: approximate starter geometry and any OSM discovery candidates.
- `source_inventory.json` and `quality_report.json`: known evidence and missing current sources.
- `mac_handoff.json`: versioned integration contract, always `UNVERIFIED`.
- `mapping.json`, `evidence/`, and `raw/`: mapping, parsed evidence, and exact source bytes for a portable handoff.

### Bring in the actual workbook

The supplied `Projects_Overlaps.xlsx` has now been imported: **10 projects, 6 starter overlap rows, 6 endpoint segments, and 4 single points**. The exact mapping is checked in at `ingestion/catalog/sperry_starter_mapping.json`. The two challenge documents are DOCX files, and their basic body text and original bytes are preserved alongside the supplied DESC and Georgia Power PDFs. See [the import status](docs/starter-status.md) for source hashes, gaps, and the current local output paths.

Run the complete import from the organizer folder (no network calls):

```powershell
.\.venv\Scripts\python.exe -m ingestion --data-dir data/live challenge --input-dir "C:\Users\badri\Downloads\Sperry-Tech-Challenge" --include-osm
```

`--include-osm` attaches existing OSM snapshots from that data directory. The import also works without supporting files and reports which are missing. Supporting utility documents are candidate evidence selected by utility, **not verified project associations or confirmed current sources**. Supplied materials are classified `PUBLIC_ASSUMED` with an explicit review flag; OSM snapshots retain their own public-access classification. Nothing in the source folder is edited.

For manual ingestion or a differently structured workbook:

```powershell
.\.venv\Scripts\python.exe -m ingestion ingest --path "C:\path\Projects_Overlaps.xlsx" --format xlsx --source-id STARTER-PROJECTS --title "Projects Overlaps" --publisher "Challenge organizers" --source-type STARTER_WORKBOOK --source-tier C --access-class PUBLIC_CONFIRMED
```

Use the resulting `parsed_path` to inspect the sheet names and raw headers. Copy and adapt `examples/starter_mapping.json`; its column names are illustrative, not a guessed official mapping. Then:

```powershell
.\.venv\Scripts\python.exe -m ingestion starter --source-version SV-REPLACE --mapping examples/starter_mapping.json
```

The mapping must name the actual project sheets, header rows, and columns. It may define multiple project sheets, with a fixed `utility` per sheet if needed. `expected_project_count: 10` checks completeness. Missing mapped columns, duplicate IDs, and unexpected project counts fail explicitly. Dates use ISO strings with cell types and number formats retained in parsed evidence; formula text is preserved, not evaluated. Blank cells remain null. CSV input uses UTF-8 and commas with no type inference.

Coordinates use explicitly named longitude/latitude columns. For a text column, replace `coordinates` with:

```json
{"column": "Coordinates", "order": "lat_lon", "separator": ";"}
```

This accepts decimal pairs such as `(32.2, -81.2); (32.4, -81.0)`. Ambiguous/DMS/formula coordinates stay in raw fields with an issue recorded and no geometry invented. One endpoint becomes a point; two become `TWO_ENDPOINT_SEGMENT` / `APPROXIMATE`. Neither represents a verified transmission route.

### Public source acquisition

The same `ingest` command supports `pdf`, `xlsx`, `csv`, `geojson`, `shapefile` (ZIP), `html`, and basic `docx` body-text snapshots for the supplied guides. Replace `--path` with `--url` for public HTTP(S) downloads. All sources require title, publisher, source ID/type/tier, and access classification. Preserve challenge documents with `--source-type CHALLENGE_DOCUMENT --source-tier C`. Preserve a current utility document with tier A and a stable source ID; changed bytes create a new version without modifying the old evidence.

For GIS, GeoJSON defaults to EPSG:4326 per its standard. Legacy declared CRS is retained. Shapefile ZIPs require one `.shp` with `.shx`/`.dbf` and either `.prj` or explicit `--source-crs EPSG:26917`. CRS conflicts fail. All geometry exports use EPSG:4326 and `[longitude, latitude]`. Invalid geometry is rejected, not silently repaired.

PDF ingestion provides page count and basic text by page. Pages without extracted text are flagged `OCR_REQUIRED` (including potentially blank pages); this is a conservative signal, not OCR. HTML snapshots retain raw bytes plus title/text, with UTF-8 replacement decoding documented in the parsed record.

### Bulk OSM discovery

```powershell
.\.venv\Scripts\python.exe -m ingestion overpass --utility DESC --region savannah
.\.venv\Scripts\python.exe -m ingestion overpass --utility GPC --region savannah
.\.venv\Scripts\python.exe -m ingestion overpass --utility DESC --region augusta
```

Each command makes one bounded regional query (plus at most two retries for transport/transient HTTP failures), saves original Overpass JSON as a SourceVersion, and exports GeoJSON under `data/geo/<source-version>/<parser-config>/`. Query text, bounding box, provider timestamp, retrieval time, tags, feature IDs, and attribution are retained. Overpass responses containing a runtime remark are treated as incomplete failures; they are not accepted as an empty successful result.

Attach a downloaded GIS/OSM source to a starter handoff:

```powershell
.\.venv\Scripts\python.exe -m ingestion starter --source-version SV-WORKBOOK --mapping examples/starter_mapping.json --geo-source-version SV-OSM
```

The local filter returns name candidates and operator-match diagnostics, including conflicting alternatives, for Mac to assess. OSM describes existing infrastructure; it does not establish a future project's route. Query regions are search windows, not utility territory polygons. Features with missing operator/owner tags can be missed. v0 exports nodes and ways; unsupported/incomplete relations are retained in raw evidence and listed as skipped, never converted into invented routes. County/voltage filtering, Nominatim, HIFLD-specific adapters, and first-party source discovery automation remain follow-up work.

Implementation references: [Overpass QL](https://wiki.openstreetmap.org/wiki/Overpass_API/Overpass_QL), [pyproj axis ordering](https://pyproj4.github.io/pyproj/stable/api/transformer.html). Keep [OpenStreetMap attribution and ODbL terms](https://www.openstreetmap.org/copyright) with exported OSM data.

### Storage and policy

`data/` is local runtime state and is gitignored. Back it up or share the complete portable handoff folder with the team; Git alone does not preserve acquired evidence. No AWS account is needed.

- `raw/<sha-prefix>/<sha256>`: unchanged content-addressed source bytes.
- `catalog.sqlite3`: SourceVersions and persisted ingestion job transitions/errors.
- `parsed/<version>/<parser-config>/`: deterministic parser output and metadata.
- `geo/`: canonical geometry exports.
- `fixtures/<package-id>/`: portable starter/Mac package, isolated by inputs and mapping.

```powershell
.\.venv\Scripts\python.exe -m ingestion catalog
```

This exports the source/job registry to `data/catalog.json`. The checked-in `sources/catalog.json` records the supplied source inventory and utility source-refresh queue; raw files remain in local storage.

SHA-256 identifies bytes. Same source ID and same bytes reuse one SourceVersion; different source IDs preserve separate provenance while sharing raw storage. Same URL/source ID with changed bytes creates another version. Duplicate ingestion skips parsing unless `--force` or the parser version/configuration changes. Job history records each acquisition attempt. Raw integrity is checked on reuse and export.

Access classifications are supplied by the acquiring person; this is enforcement of recorded classification, not automatic CEII detection. `CEII` is rejected before reading/downloading. `ACCESS_UNCLEAR` stays local, ends in `NEEDS_REVIEW`, and cannot export a handoff. `PUBLIC_ASSUMED` exports carry a review flag. Re-uploading the same source cannot silently promote its access class; a reviewed access-class update workflow is not implemented yet. There is no remote AI path in v0.

See [the handoff contract](docs/handoff.md) for integration details and limitations.
