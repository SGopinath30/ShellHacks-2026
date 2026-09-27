# Dell → Mac contract v0.1.0

`mac_handoff.json` is a JSON object with `schema_version`, `package_id`, `source_records`, `project_seeds`, and `geometry_candidates`. It also carries `association_status: UNVERIFIED`, `data_label: STARTER_DATA`, `currentness: UNVERIFIED_CURRENTNESS`, `synthetic`, and `review_required`. Consumers must not present these as source-verified findings. ASUS may use the fixture for development only.

Each source record includes `source_id`, `source_version_id`, title, publisher, type, tier, access class, retrieval time, MIME type, SHA-256, byte size, and `raw_path`. HTTP acquisitions also retain requested/resolved URLs and server metadata. `raw_path` resolves relative to the portable package folder as well as the original storage root. Its SHA-256 must match the bytes. PDF evidence includes page numbers; workbook seeds include sheet/row locators. Source ID identifies a logical publication; source version ID identifies that publication's bytes.

Each project seed retains its original starter ID and raw fields, plus a stable `project_candidate_id`, utility alias for searching, raw utility, raw schedule, raw coordinates, source version ID, and source locator. `record_origin` remains `STARTER_PACKAGE`. No newer facts overwrite these rows. Unknown utilities remain raw and are reported as missing recognized utility IDs. Synthetic demo seeds additionally have `synthetic: true`.

Every geometry candidate includes:

| Field | Meaning |
| --- | --- |
| `geometry_candidate_id` | Stable ID for this project/source/geometry candidate |
| `project_candidate_id` | Seed this candidate might correspond to |
| `source_version_id` | Evidence snapshot providing the geometry |
| `provider`, `provider_feature_id` | Provider and original feature reference |
| `feature_name`, `operator_raw`, `feature_type` | Provider/source values |
| `geometry` | GeoJSON geometry, canonical longitude/latitude order |
| `source_crs`, `canonical_crs` | Original CRS and EPSG:4326 output CRS |
| `geometry_origin`, `geometry_quality` | Approximate endpoint segment/point or existing provider geometry |
| `association_status` | Always `UNVERIFIED` |
| `discovery_method`, `query_metadata` | Reproducible acquisition/filtering context |
| `retrieved_at` | Source retrieval timestamp |

An OSM candidate retains all provider tags in `provider_properties`. `operator_match` is a search diagnostic, not ownership verification. `PROVIDER_GEOMETRY` describes the geometry representation; it is not an accuracy certification. Missing candidates are valid outputs requiring further discovery. Multiple same-name candidates remain separate.

The same workbook/mapping/source artifacts produce identical exported records. Timestamps in SourceVersions describe first retrieval of those bytes; subsequent download checks appear in the job log. Local jobs use `DISCOVERED → DOWNLOADING → DOWNLOADED → PARSING → PARSED → READY_FOR_INTELLIGENCE`, or `NEEDS_REVIEW` for unclear access. Cached parses skip `PARSING`. Any failed acquisition/parse records `FAILED`, an error code, message, and retryability.

The handoff is file based. There is no Mac API integration or acceptance/rejection state machine yet. Mac should create its own validation results referencing Dell IDs, leaving these candidate records unchanged. County/landmark checks, schedule interpretation, normalized project taxonomy, reconciliation, and overlap belong downstream.

The v0 quality report deliberately lists all starter seeds as needing a confirmed current first-party source. Supplied utility PDFs can now be included as `supporting` evidence; the CLI accepts repeatable `--supporting-source-version` arguments. The source inventory lists same-utility documents under `utility_document_candidates`, with their association and currentness explicitly unverified. The `challenge` command does this automatically for the supplied organizer folder. These documents travel in the package's raw/evidence folders. Associating individual facts with these PDFs and checking for newer publications remain downstream/discovery work. Do not interpret zero current sources as absence of supplied planning evidence.

The exact organizer mapping exposes overlap IDs, project IDs, `raw_distance_mi`, and `raw_time_gap_days` without calculating or changing those values. Formula-based center coordinates stay as formula strings in `raw_fields`; geometry uses the provided endpoint columns only. Original workbook cell types and number formats remain in the parsed evidence. Single-point starter project IDs appear in the quality report so missing endpoints cannot be mistaken for complete routes.
