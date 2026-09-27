"""Build API-shaped review records and isolated starter fixtures."""

import json
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
SOURCE_BACKED = OUT / "source_backed_needs_review"
FIXTURES = OUT / "starter_fixtures"
STARTER = next((ROOT / "data" / "live" / "fixtures").glob("PKG-*/"))


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


source_backed = [
    {
        "project_id": "DESC-WINNSBORO-WEST-2025-208-E",
        "utility_id": "DESC",
        "project_name": "Winnsboro West 230/115 kV Substation",
        "project_type": "substation",
        "status": "in_progress",
        "voltage_kv": 230,
        "location_text": "Winnsboro West, Fairfield County, South Carolina; exact substation parcel requires georeferencing from DESC Exhibit B",
        "geometry": {"type": "Point", "coordinates": [-81.088056, 34.376944]},
        "geometry_origin": "CENTER_POINT",
        "geometry_quality": "UNRESOLVED",
        "validation_state": "NEEDS_REVIEW",
        "source_crs": "EPSG:4326",
        "schedule": {"type": "UNKNOWN"},
        "evidence": [
            {
                "source_id": "SCPSC-2025-208-E-2026-08-14",
                "source_name": "DESC quarterly update, SCPSC Docket 2025-208-E",
                "source_url": "https://dms.psc.sc.gov/Attachments/Matter/72042102-313d-484f-b112-50ba66742d92",
                "page_or_row": "page 1",
                "snippet": "DESC has started clearing and grading for the Winnsboro West Substation. Projected completion is January 1, 2028.",
            },
            {
                "source_id": "SCPSC-2025-208-E-EXHIBIT-B",
                "source_name": "DESC Exhibits A and B, SCPSC Docket 2025-208-E",
                "source_url": "https://dms.psc.sc.gov/Attachments/Matter/bed0f283-a5b8-4c56-9c36-202d635a503c",
                "page_or_row": "page 3, Exhibit B",
                "snippet": "Exhibit B depicts Winnsboro West; coordinates in this JSON are a Winnsboro town reference point, not the substation site.",
            },
            {
                "source_id": "WIKIDATA-Q2317192",
                "source_name": "Wikidata Winnsboro town coordinate, citing US Census Gazetteer",
                "source_url": "https://www.wikidata.org/wiki/Q2317192",
                "snippet": "Town reference coordinate only; it does not locate the Winnsboro West substation.",
            },
        ],
        "is_fixture": False,
    },
    {
        "project_id": "GPC-BIG-OGEECHEE-500-230-2026",
        "utility_id": "GPC",
        "project_name": "Big Ogeechee 500/230 kV Substation",
        "project_type": "substation",
        "status": "unknown",
        "voltage_kv": 500,
        "location_text": "West Chatham County, Georgia, near Little Ogeechee Substation; exact Big Ogeechee site requires confirmation",
        "geometry": {"type": "Point", "coordinates": [-81.25315, 32.00679]},
        "geometry_origin": "CENTER_POINT",
        "geometry_quality": "UNRESOLVED",
        "validation_state": "NEEDS_REVIEW",
        "source_crs": "EPSG:4326",
        "schedule": {"type": "UNKNOWN"},
        "evidence": [
            {
                "source_id": "GPC-BIG-OGEECHEE-2026-06-17",
                "source_name": "Georgia Power Big Ogeechee project update",
                "source_url": "https://www.georgiapower.com/news-hub/community/big-ogeechee-substation-power-savannah-area-growth-storm-hardened-coastal-grid.html",
                "snippet": "Georgia Power describes Big Ogeechee in West Chatham County and expected it to come online in summer 2026; current service status needs confirmation.",
            },
            {
                "source_id": "OSM-GPC-savannah",
                "source_name": "OpenStreetMap Little Ogeechee Substation, way 121701191",
                "source_url": "https://www.openstreetmap.org/way/121701191",
                "page_or_row": "way 121701191",
                "snippet": "Point is the nearby Little Ogeechee Substation reference location, not a surveyed Big Ogeechee location.",
            },
        ],
        "source_version_ids": ["SV-77849dfbe8c38c861c0776f2"],
        "is_fixture": False,
    },
]

for record in source_backed:
    write(SOURCE_BACKED / f"{record['project_id']}.json", record)

projects = json.loads((STARTER / "starter_projects.json").read_text(encoding="utf-8"))
candidates = json.loads((STARTER / "geometry_candidates.json").read_text(encoding="utf-8"))
for project in projects:
    starter_id = project["starter_id"]
    geometry = next(
        candidate["geometry"]
        for candidate in candidates
        if candidate["project_candidate_id"] == project["project_candidate_id"]
        and candidate["provider"] == "STARTER_PACKAGE"
    )
    name = project["project_name"]
    lower = name.lower()
    project_type = "substation" if "substation" in lower or " sub" in lower else "rebuild" if "rebuild" in lower else "transmission_line" if "line" in lower else "other"
    raw_date = project.get("raw_in_service_date")
    try:
        date = datetime.strptime(raw_date, "%m/%d/%Y").date().isoformat()
        schedule = {"type": "IN_SERVICE_GAP", "in_service_date": date}
    except (TypeError, ValueError):
        schedule = {"type": "UNKNOWN"}
    origin = "TWO_ENDPOINT_SEGMENT" if geometry["type"] == "LineString" else "SINGLE_LOCATED_POINT"
    endpoints = [part for part in (project.get("endpoint_name_a"), project.get("endpoint_name_b")) if part]
    record = {
        "project_id": f"FIXTURE-{starter_id}",
        "utility_id": project["utility"],
        "project_name": name,
        "project_type": project_type,
        "status": "unknown",
        "location_text": f"{' to '.join(endpoints)}, {project['state_raw']} (starter workbook; location unverified)",
        "geometry": geometry,
        "geometry_origin": origin,
        "geometry_quality": "APPROXIMATE",
        "validation_state": "NEEDS_REVIEW",
        "source_crs": "EPSG:4326",
        "schedule": schedule,
        "evidence": [{
            "source_id": "STARTER-PROJECTS",
            "source_name": "Projects_Overlaps.xlsx (organizer starter workbook)",
            "page_or_row": f"{project['source_locator']['sheet']} row {project['source_locator']['row_number']}",
            "snippet": f"Starter project {starter_id}: {name}; raw in-service date {raw_date or 'blank'}. These are unverified fixture values.",
        }],
        "source_version_ids": [project["source_version_id"]],
        "is_fixture": True,
    }
    write(FIXTURES / f"{record['project_id']}.json", record)

print(f"Wrote {len(source_backed)} source-backed review records and {len(projects)} fixtures")
