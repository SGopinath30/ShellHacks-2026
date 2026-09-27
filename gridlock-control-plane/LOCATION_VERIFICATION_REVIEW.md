# Location verification review — 2026-09-27

Outcome: evidence review completed; neither project is ready for a location-verification submission. No production records were changed.

## Winnsboro West (DESC)

The latest quarterly filing located, dated August 14, 2026, reports clearing and grading underway and projected completion January 1, 2028. This supports the existing `in_progress` status as of that filing; it is not a same-day field observation.

Source: https://dms.psc.sc.gov/Attachments/Matter/72042102-313d-484f-b112-50ba66742d92 (page 1).

Exhibit B identifies the proposed substation on a regional map. No explicit site coordinates or parcel identifier were established in this review. PDF text was inspected; visual rendering inspection was blocked by the local image tool sandbox failure. The current town reference point must not be accepted as the site.

Location source: https://dms.psc.sc.gov/Attachments/Matter/bed0f283-a5b8-4c56-9c36-202d635a503c (page 3, Exhibit B).

Remaining evidence: georeferenced utility site geometry or a parcel/GIS feature positively matched to this project, with source URL, feature ID, CRS, and defensible accuracy.

## Big Ogeechee (Georgia Power)

Georgia Power's June 17, 2026 announcement describes expected summer completion in west Chatham County and distinguishes Big Ogeechee from nearby Little Ogeechee. Searches did not establish a later authoritative commissioning/current-status update or exact Big Ogeechee coordinates. Keep `unknown` until current evidence resolves status; do not turn an elapsed forecast into a construction or operating claim.

Source: https://www.georgiapower.com/news-hub/community/big-ogeechee-substation-power-savannah-area-growth-storm-hardened-coastal-grid.html

The 2025 SERTP fourth-quarter presentation labels the proposed site location approximate; it does not establish verification-grade geometry in this review.

Source: https://www.southeasternrtp.com/docs/general/2025/2025_SERTP_4th_Qtr_Presentation.pdf

Remaining evidence: exact project-specific site geometry and a dated utility/regulatory record confirming current construction or commissioning status. Existing Little Ogeechee reference coordinates are insufficient.

## Submission gate

`POST /api/v1/projects/{project_id}/verify-location` requires actual geometry and supporting source evidence. Neither record has a defensible complete payload from this research, so no verification POST was sent. DESC's supported status is already stored and needs no redundant write. Do not claim human ASUS attestation for automated research.

Implementation limitation: the verification request's status enum has no completed/operational value. If authoritative evidence establishes commissioning, address that contract gap rather than mislabeling the project as still under construction.

## Live result

The review queue contains two unresolved records. Qualified DESC–GPC pairs: zero. Pair assessment reports reference-point separation of 263,319.178 meters, versus a strict 40,000-meter maximum. This is explicitly REFERENCE_POINT_SEPARATION, not verified project distance. The large separation is a screening reason to investigate a different pair, not an exact measurement of these sites.

Verification alone does not ensure an opportunity: both statuses must be eligible, geometry must be accepted and sufficiently reliable, and actual project distance must be under 40 km.
