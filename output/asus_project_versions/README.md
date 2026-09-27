# ASUS project-version handoff

Each `.json` file contains one object shaped for `POST /api/v1/project-versions` in the [live OpenAPI schema](https://gridlock-api-production.up.railway.app/openapi.json), checked on 2026-09-26. ASUS handles uploads. No API key is needed in these files.

## Source-backed records — locations need review before upload

| File | Verified from current source | Still needs review |
| --- | --- | --- |
| `source_backed_needs_review/DESC-WINNSBORO-WEST-2025-208-E.json` | DESC's August 2026 PSC filing confirms the substation and that clearing and grading started. Exhibit B shows the project area. | The Point is Winnsboro's town reference coordinate, **not** the substation parcel. Confirm exact site and in-service timing. The filing's projected completion date is not automatically an in-service date. |
| `source_backed_needs_review/GPC-BIG-OGEECHEE-500-230-2026.json` | Georgia Power's June 2026 update confirms the 500/230 kV substation in West Chatham County near Little Ogeechee. | The Point locates the **existing Little Ogeechee** substation as a nearby reference, **not** Big Ogeechee. Confirm Big Ogeechee's site and whether it entered service after the June update. |

Both records use `geometry_origin: CENTER_POINT`, `geometry_quality: UNRESOLVED`, and `validation_state: NEEDS_REVIEW`. Their points are broad map references. **Do not use them for distance matching or production upload until the coordinates are replaced with verified project locations.** Their schedules are `UNKNOWN` because the available statements give projected completion or a broad season, not a confirmed in-service date or a bounded construction period.

## Starter fixtures — separate

`starter_fixtures/` contains the 10 organizer workbook projects, each with `is_fixture: true`, `validation_state: NEEDS_REVIEW`, and its original row as evidence. A two-endpoint geometry is an approximate straight segment (`TWO_ENDPOINT_SEGMENT`), and a single workbook coordinate is `SINGLE_LOCATED_POINT`. These are development fixtures and do not establish current utility project facts or routes. `FIXTURE-` prefixes keep their IDs distinct from source-backed projects.

The supplied Georgia Power IRP PDF contains pages marked CEII/confidential despite its public-disclosure title, so it was not used for these export records. The supplied 2024–2028 DESC listing was also not used as current status evidence. Source-backed records instead cite a [Georgia Power project update](https://www.georgiapower.com/news-hub/community/big-ogeechee-substation-power-savannah-area-growth-storm-hardened-coastal-grid.html) and [DESC's August 2026 PSC filing](https://dms.psc.sc.gov/Attachments/Matter/72042102-313d-484f-b112-50ba66742d92).

Run `python output/asus_project_versions/build.py` from the repository root to regenerate all records. The current OpenAPI schema is saved as `openapi.json` for validation only; it is not a project upload file.
