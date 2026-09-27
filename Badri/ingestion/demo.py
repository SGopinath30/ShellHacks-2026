"""Offline smoke demo. These records are invented, never challenge data."""
from openpyxl import Workbook

from ingestion.jobs.handoff import export_starter
from ingestion.jobs.pipeline import ingest

DEMO_MAPPING = {
    "expected_project_count": 2,
    "projects": [{"sheet": "Projects", "header_row": 1,
                  "columns": {"starter_id": "ID", "utility": "Utility", "project_name": "Project",
                              "raw_in_service_date": "In service"},
                  "coordinates": {"points": [{"longitude": "A lon", "latitude": "A lat"},
                                             {"longitude": "B lon", "latitude": "B lat"}]}}],
    "overlaps": [{"sheet": "Overlaps", "header_row": 1}],
}


def run_demo(store):
    path = store.root / "demo-inputs" / "SYNTHETIC_ONLY.xlsx"
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        workbook = Workbook()
        projects = workbook.active
        projects.title = "Projects"
        projects.append(["ID", "Utility", "Project", "In service", "A lon", "A lat", "B lon", "B lat"])
        projects.append(["SYNTHETIC_DESC_1", "DESC", "Synthetic Alpha - Beta 230 kV", "2028 (demo)", -81.2, 32.2, -81.0, 32.4])
        projects.append(["SYNTHETIC_GPC_1", "GPC", "Synthetic Gamma substation", "TBD (demo)", -81.4, 32.1, None, None])
        overlaps = workbook.create_sheet("Overlaps")
        overlaps.append(["Project A", "Project B", "Original fixture note"])
        overlaps.append(["SYNTHETIC_DESC_1", "SYNTHETIC_GPC_1", "Invented fixture claim; never calculated or verified"])
        workbook.save(path)
        workbook.close()
    source, parsed, job = ingest(store, path=path, file_format="xlsx", metadata={
        "source_id": "SYNTHETIC-DEMO", "title": "Synthetic ingestion smoke fixture",
        "publisher": "SYNCHRO development", "source_type": "SYNTHETIC", "source_tier": "C",
        "access_class": "PUBLIC_CONFIRMED"})
    output, report = export_starter(store, source, parsed, DEMO_MAPPING)
    return {"synthetic": True, "output_dir": str(output), "job": job, "quality_report": report}
