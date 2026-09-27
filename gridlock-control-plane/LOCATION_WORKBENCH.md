# Location Workbench

Open `/api/v1/location-workbench` on the backend to see the Excluded Projects queue, compare two records, and inspect qualified DESC–Georgia Power pairs. The page is read-only. ASUS submits source-backed verification through the protected API; the shared write key never goes into the page.

## Readiness and distance

`GET /api/v1/location-review-queue` returns current project versions that need review. Each row has `blockers`, `coordinate_role`, `matching_eligible`, and `qualified_ready`. Starter fixtures are hidden unless `include_fixtures=true`.

`GET /api/v1/pair-assessments?project_a=...&project_b=...` explains both records and any measured separation. If either coordinate is a reference center point, `distance.kind` is `REFERENCE_POINT_SEPARATION`. That number must never be presented as a verified project-to-project distance. `within_configured_maximum` describes the supplied geometries only. The default maximum is strictly under 40,000 meters.

`GET /api/v1/qualified-pairs` searches current DESC and GPC opportunities using the existing PostGIS engine. A qualified pair requires two different utilities, non-fixture records, eligible project statuses, `ACCEPTED` validation, `HIGH` or `AUTHORITATIVE` geometry, project-specific geometry rather than a reference center point, and measured distance strictly under the configured maximum. The response is empty until real records satisfy these gates. It never fabricates a nearby pair from reference coordinates.

## Verification write

`POST /api/v1/projects/{project_id}/verify-location` creates a new immutable `ProjectVersion` and an append-only location verification record in one transaction. Send the current `base_version_id` to reject stale reviews. A status change requires separate status evidence. Coordinates are GeoJSON `[longitude, latitude]` in EPSG:4326. The reviewer selects a geometry quality supported by the source: `APPROXIMATE` remains in review; `HIGH` and `AUTHORITATIVE` become `ACCEPTED`.

Example request shape (illustrative values only; **do not upload these coordinates**):

```json
{
  "base_version_id": "PV-from-current-project",
  "actor_id": "asus-reviewer-id",
  "actor_role": "Location Reviewer",
  "reason": "Matched the project parcel to the utility GIS feature.",
  "location_text": "Source-backed project site description",
  "geometry": {"type": "Point", "coordinates": [-81.0, 32.0]},
  "geometry_origin": "UTILITY_GIS",
  "geometry_quality": "HIGH",
  "geometry_evidence": {
    "source_id": "utility-gis-feature-id",
    "source_name": "Utility project GIS",
    "source_url": "https://example.com/project-gis",
    "page_or_row": "feature ID"
  },
  "status": "in_progress",
  "status_evidence": {
    "source_id": "status-update-id",
    "source_name": "Utility status update",
    "source_url": "https://example.com/status-update",
    "snippet": "Source statement supporting the current status"
  }
}
```

The server retains prior evidence, clears any old proxy center point, and records the old/new version IDs, reviewer, reason, and new evidence. `GET /api/v1/projects/{project_id}/location-verifications` reads that history; it requires `X-API-Key` when configured. The reviewer identity is currently client asserted because the service has a shared API key rather than individual sign-in. A source URL and reviewer attestation are required; the service does not independently inspect an external map or certify its accuracy.

The existing Decision Ledger remains the manager workflow after a qualified opportunity appears. If a project version used by a manager decision changes, the ledger records the version change and flags the pair for review.
