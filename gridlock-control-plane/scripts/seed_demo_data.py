"""
Seeds the in-memory repo with the demo pair from PRD section 9
(Riverbend 230-kV Line / Northgate Substation) plus a couple of decoys, so
the API and frontend have something real to point at before ingestion +
extraction land.

Run with the API server already started, or import `seed()` directly in a
test/dev shell.
"""

from datetime import date

from app.db import repo
from app.matching import compute_matches
from app.models import (
    LineGeometry,
    PointGeometry,
    ProjectRecord,
    ProjectStatus,
    ProjectType,
    SourceEvidence,
)


def seed() -> None:
    riverbend = ProjectRecord(
        project_id="A-017",
        utility_id="UTILITY-A",
        project_name="North River 230kV Rebuild",
        project_type=ProjectType.TRANSMISSION_LINE,
        voltage_kv=230,
        start_date=date(2028, 3, 1),
        end_date=date(2029, 8, 31),
        status=ProjectStatus.PLANNED,
        geometry=LineGeometry(coordinates=[(-84.40, 33.75), (-84.30, 33.80)]),
        location_text="North River corridor, between County Rd 9 and the Utility A/B seam",
        evidence=SourceEvidence(
            source_id="utility-a-2026-plan",
            source_name="Utility A 2026 Transmission Plan",
            page_or_row="page 84",
            snippet="Construct new 230-kV rebuild along the North River corridor...",
        ),
        extraction_confidence=0.96,
    )

    northgate = ProjectRecord(
        project_id="B-044",
        utility_id="UTILITY-B",
        project_name="Northgate Substation Upgrade",
        project_type=ProjectType.SUBSTATION,
        voltage_kv=230,
        start_date=date(2028, 10, 1),
        end_date=date(2030, 6, 1),
        status=ProjectStatus.PLANNED,
        geometry=PointGeometry(coordinates=(-84.22, 33.83)),
        location_text="Northgate Substation site, near the Utility A/B boundary",
        evidence=SourceEvidence(
            source_id="utility-b-2026-plan",
            source_name="Utility B 2026 Capital Plan",
            page_or_row="page 117",
            snippet="Upgrade Northgate substation to accommodate additional 230-kV capacity...",
        ),
        extraction_confidence=0.93,
    )

    decoy = ProjectRecord(
        project_id="A-021",
        utility_id="UTILITY-A",
        project_name="Distant Feeder Upgrade",
        project_type=ProjectType.UPGRADE,
        voltage_kv=69,
        start_date=date(2031, 1, 1),
        end_date=date(2031, 12, 1),
        status=ProjectStatus.PLANNED,
        geometry=PointGeometry(coordinates=(-90.0, 30.0)),
        location_text="Unrelated feeder project, far from the A/B seam",
        evidence=SourceEvidence(
            source_id="utility-a-2026-plan",
            source_name="Utility A 2026 Transmission Plan",
            page_or_row="page 12",
        ),
        extraction_confidence=0.9,
    )

    for p in (riverbend, northgate, decoy):
        repo.upsert_project(p)

    matches = compute_matches(
        repo.list_projects(),
        spatial_threshold_miles=25,
        temporal_min_overlap_days=90,
        seam_buffer_miles=20,
        boundary_distances={("A-017", "B-044"): 12.0},  # from PRD example: 12 miles from boundary
    )
    repo.replace_matches(matches)
    print(f"Seeded {len(repo.list_projects())} projects, {len(matches)} matches.")


if __name__ == "__main__":
    seed()
