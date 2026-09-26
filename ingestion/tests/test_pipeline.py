from copy import deepcopy
from datetime import datetime
from io import BytesIO

import pytest
from openpyxl import Workbook
from pypdf import PdfWriter

from ingestion.common import IngestionError, read_json
from ingestion.demo import DEMO_MAPPING, run_demo
from ingestion.jobs.handoff import export_starter
from ingestion.jobs.pipeline import ingest
from ingestion.parsers.csv import parse_csv
from ingestion.parsers.pdf import parse_pdf
from ingestion.parsers.starter import map_starter
from ingestion.versioning.sources import Store


def metadata(access="PUBLIC_CONFIRMED"):
    return {"source_id": "TEST-WORKBOOK", "title": "Synthetic test", "publisher": "Test suite",
            "source_type": "SYNTHETIC", "source_tier": "C", "access_class": access}


def workbook_bytes(count=10):
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Projects"
    sheet.append(["ID", "Utility", "Project", "In service", "A lon", "A lat", "B lon", "B lat", "Untouched"])
    for i in range(count):
        sheet.append([f"SYNTHETIC_{i}", "Dominion Energy SC", f"Synthetic A{i} - B{i} 230 kV", datetime(2028, 1, 2),
                      -81.2, 32.2, -81.0, 32.4, "=1+1"])
    overlaps = workbook.create_sheet("Overlaps")
    overlaps.append(["A", "B", "Note"])
    overlaps.append(["SYNTHETIC_0", "SYNTHETIC_1", "  preserve spaces  "])
    output = BytesIO()
    workbook.save(output)
    workbook.close()
    return output.getvalue()


def ingest_workbook(tmp_path, access="PUBLIC_CONFIRMED"):
    path = tmp_path / "workbook.xlsx"
    path.write_bytes(workbook_bytes())
    store = Store(tmp_path / "data")
    source, parsed, job = ingest(store, metadata=metadata(access), path=path, file_format="xlsx")
    return store, source, parsed, job, path


def test_ten_rows_raw_values_and_deterministic_portable_exports(tmp_path):
    store, source, parsed, job, path = ingest_workbook(tmp_path)
    mapping = deepcopy(DEMO_MAPPING)
    mapping["expected_project_count"] = 10
    output, report = export_starter(store, source, parsed, mapping)
    first = (output / "mac_handoff.json").read_bytes()
    output2, _ = export_starter(store, source, parsed, mapping)
    assert (output2 / "mac_handoff.json").read_bytes() == first
    projects = read_json(output / "starter_projects.json")
    assert len(projects) == report["project_count"] == 10
    assert projects[0]["raw_fields"]["Untouched"] == "=1+1"
    assert projects[0]["raw_in_service_date"] == "2028-01-02T00:00:00"
    assert projects[0]["utility_raw"] == "Dominion Energy SC"
    assert projects[0]["utility"] == "DESC"
    assert read_json(output / "starter_overlaps.json")[0]["raw_fields"]["Note"] == "  preserve spaces  "
    assert (output / source["raw_path"]).read_bytes() == path.read_bytes()
    assert store.raw_bytes(source) == path.read_bytes()
    candidate = read_json(output / "geometry_candidates.json")[0]
    assert candidate["geometry"]["coordinates"] == [[-81.2, 32.2], [-81.0, 32.4]]
    assert candidate["geometry_quality"] == "APPROXIMATE"
    assert candidate["geometry_origin"] == "TWO_ENDPOINT_SEGMENT"
    assert candidate["association_status"] == "UNVERIFIED"
    assert "verified" not in candidate
    assert job["status"] == "READY_FOR_INTELLIGENCE"
    assert report["projects_with_current_first_party_source"] == 0


def test_duplicate_skips_parse_and_changed_bytes_make_new_version(tmp_path):
    store, source, _, _, path = ingest_workbook(tmp_path)
    same, _, job = ingest(store, metadata=metadata(), path=path, file_format="xlsx")
    assert same == source
    assert job["disposition"] == "DUPLICATE_SOURCE_VERSION"
    assert job["parse_cached"] is True
    assert "PARSING" not in [event["status"] for event in job["history"]]
    path.write_bytes(workbook_bytes(9))
    newer, _, _ = ingest(store, metadata=metadata(), path=path, file_format="xlsx")
    assert newer["source_version_id"] != source["source_version_id"]
    assert len(store.versions()) == 2


def test_ceii_rejected_before_reading_or_storing(tmp_path):
    store = Store(tmp_path)
    with pytest.raises(IngestionError, match="CEII"):
        ingest(store, metadata=metadata("CEII"), path=tmp_path / "does-not-exist", file_format="pdf")
    assert store.versions() == []
    assert not (tmp_path / "raw").exists()
    assert store.jobs()[-1]["error"]["error_code"] == "CEII_REJECTED"


def test_unclear_cannot_export_or_be_promoted_by_reupload(tmp_path):
    store, source, parsed, job, path = ingest_workbook(tmp_path, "ACCESS_UNCLEAR")
    assert job["status"] == "NEEDS_REVIEW"
    with pytest.raises(IngestionError, match="quarantined"):
        export_starter(store, source, parsed, DEMO_MAPPING)
    same, _, _ = ingest(store, metadata=metadata(), path=path, file_format="xlsx")
    assert same["access_class"] == "ACCESS_UNCLEAR"
    assert not (store.root / "fixtures").exists()


def test_raw_tamper_detected(tmp_path):
    store, source, _, _, path = ingest_workbook(tmp_path)
    (store.root / source["raw_path"]).write_bytes(b"tampered")
    with pytest.raises(IngestionError) as error:
        ingest(store, metadata=metadata(), path=path, file_format="xlsx")
    assert error.value.code == "RAW_INTEGRITY_ERROR"
    assert store.jobs()[-1]["status"] == "FAILED"


def test_bad_mapping_and_count_are_explicit_errors(tmp_path):
    _, source, parsed, _, _ = ingest_workbook(tmp_path)
    with pytest.raises(IngestionError, match="Expected 2, parsed 10"):
        map_starter(parsed, DEMO_MAPPING, source)
    mapping = deepcopy(DEMO_MAPPING)
    mapping["projects"][0]["columns"]["project_name"] = "Does not exist"
    with pytest.raises(IngestionError, match="Missing mapped column"):
        map_starter(parsed, mapping, source)


def test_bad_coordinate_keeps_row_without_inventing_geometry(tmp_path):
    _, source, parsed, _, _ = ingest_workbook(tmp_path)
    parsed["sheets"][0]["rows"][1]["values"][5] = 120
    mapping = deepcopy(DEMO_MAPPING)
    mapping["expected_project_count"] = 10
    projects, _, candidates = map_starter(parsed, mapping, source)
    assert len(projects) == 10
    assert len(candidates) == 9
    assert projects[0]["geometry_issue"]["error_code"] == "INVALID_COORDINATE"


def test_csv_keeps_strings_and_pdf_flags_blank_pages_for_ocr():
    parsed = parse_csv(b'ID,Date\r\n001," Q1 2028 "\r\n')
    assert parsed["sheets"][0]["rows"][1]["values"] == ["001", " Q1 2028 "]
    writer = PdfWriter()
    writer.add_blank_page(width=100, height=100)
    output = BytesIO()
    writer.write(output)
    pdf = parse_pdf(output.getvalue())
    assert pdf["page_count"] == 1
    assert pdf["status"] == "OCR_REQUIRED"


def test_demo_is_repeatable_and_explicitly_synthetic(tmp_path):
    store = Store(tmp_path)
    first, second = run_demo(store), run_demo(store)
    assert first["synthetic"] is True
    assert first["output_dir"] == second["output_dir"]
    assert second["job"]["parse_cached"] is True
    assert second["quality_report"]["starter_points"] == 1
    assert second["quality_report"]["starter_two_endpoint_segments"] == 1
