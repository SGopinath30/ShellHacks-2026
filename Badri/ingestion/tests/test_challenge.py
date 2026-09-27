from io import BytesIO
from pathlib import Path
from zipfile import ZipFile

import pytest
from openpyxl import Workbook
from pypdf import PdfWriter

from ingestion.challenge import SUPPORTING, run_challenge
from ingestion.common import IngestionError, digest, read_json
from ingestion.demo import DEMO_MAPPING
from ingestion.geospatial.candidate_builder import build_candidates
from ingestion.geospatial.overpass import convert_response
from ingestion.jobs.handoff import export_starter
from ingestion.parsers.docx import parse_docx
from ingestion.versioning.sources import Store


def setup_challenge(folder):
    folder.mkdir()
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "projects"
    sheet.append(["project_id", "utility", "state", "project_name", "name_a", "lat_a", "lon_a",
                  "name_b", "lat_b", "lon_b", "lat_center", "lon_center", "in_service_date"])
    for i in range(10):
        sheet.append([f"TEST_{i}", "DESC" if i < 5 else "GPC", "SC" if i < 5 else "GA",
                      "TEST: Alpha - Beta 230KV", "Alpha Sub", 32.2, -81.2, "Beta Sub",
                      None if i < 4 else 32.4, None if i < 4 else -81.0,
                      f"=AVERAGE(F{i+2},I{i+2})", f"=AVERAGE(G{i+2},J{i+2})", "12/31/2025"])
    overlap = workbook.create_sheet("overlaps")
    overlap.append(["overlap_id", "distance_mi", "time_gap (day)", "project_id_a", "project_id_b"])
    for i in range(6):
        overlap.append([f"OVL_{i}", 4.09, 3074, "TEST_0", f"TEST_{i+1}"])
    workbook.save(folder / "Projects_Overlaps.xlsx")
    workbook.close()
    for _, relative, file_format, *_ in SUPPORTING:
        path = folder / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        if file_format == "docx":
            with ZipFile(path, "w") as archive:
                archive.writestr("word/document.xml", '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>Test public-source guide</w:t></w:r></w:p></w:body></w:document>')
        else:
            writer = PdfWriter()
            writer.add_blank_page(width=100, height=100)
            writer.write(path)


def test_actual_sheet_layout_and_supporting_evidence_round_trip(tmp_path):
    folder = tmp_path / "input"
    setup_challenge(folder)
    before = digest((folder / "Projects_Overlaps.xlsx").read_bytes())
    store = Store(tmp_path / "data")
    result = run_challenge(store, folder)
    assert result["quality_report"]["project_count"] == 10
    assert result["quality_report"]["overlap_fixture_count"] == 6
    assert result["quality_report"]["starter_two_endpoint_segments"] == 6
    assert result["quality_report"]["starter_points"] == 4
    assert result["quality_report"]["supporting_source_count"] == 4
    assert result["missing_supporting_files"] == []
    assert result["source_sha256"] == before == digest((folder / "Projects_Overlaps.xlsx").read_bytes())
    output = Path(result["output_dir"])
    package = read_json(output / "mac_handoff.json")
    assert package["review_required"] is True
    assert len(package["source_records"]) == 5
    for record in package["source_records"]:
        assert digest((output / record["raw_path"]).read_bytes()) == record["sha256"]
    projects = read_json(output / "starter_projects.json")
    assert projects[0]["raw_fields"]["lat_center"] == "=AVERAGE(F2,I2)"
    assert projects[0]["endpoint_name_a"] == "Alpha Sub"
    overlaps = read_json(output / "starter_overlaps.json")
    assert overlaps[0]["raw_distance_mi"] == 4.09
    assert overlaps[0]["raw_time_gap_days"] == 3074
    inventory = read_json(output / "source_inventory.json")
    assert len(inventory[0]["utility_document_candidates"]) == 1
    assert inventory[0]["utility_document_candidates"][0]["association_status"] == "UNVERIFIED"
    rerun = run_challenge(store, folder)
    assert rerun["output_dir"] == result["output_dir"]
    assert rerun["workbook_job"]["parse_cached"] is True
    assert len(store.versions()) == 5


def test_unclear_supporting_source_blocks_whole_handoff(tmp_path):
    store = Store(tmp_path)
    source, _ = store.preserve(b"workbook", {"source_id": "W", "title": "Test", "publisher": "Test",
                                         "source_type": "STARTER_WORKBOOK", "source_tier": "C", "access_class": "PUBLIC_CONFIRMED"})
    unclear, _ = store.preserve(b"unclear", {**source, "source_id": "U", "access_class": "ACCESS_UNCLEAR"})
    with pytest.raises(IngestionError, match="quarantined"):
        export_starter(store, source, {}, DEMO_MAPPING, supporting=[(unclear, {})])
    assert not (tmp_path / "fixtures").exists()


def test_explicit_endpoint_names_avoid_project_title_prefixes():
    parsed = convert_response({"elements": [{"type": "node", "id": 1, "lon": -81.2, "lat": 32.2,
                                              "tags": {"name": "Alpha Substation", "power": "substation"}}]})
    source = {"source_version_id": "SV-TEST", "source_type": "SYNTHETIC", "publisher": "Test", "retrieved_at": "test"}
    project = {"project_candidate_id": "CP-TEST", "project_name": "SAV: Alpha - Beta 230KV",
               "endpoint_name_a": "Alpha Sub", "endpoint_name_b": "Beta", "utility": "GPC"}
    candidates = build_candidates([project], parsed, source)
    assert len(candidates) == 1
    assert candidates[0]["query_metadata"]["matched_names"] == ["alpha"]


def test_docx_keeps_table_paragraph_locators_and_raw_text():
    buffer = BytesIO()
    with ZipFile(buffer, "w") as archive:
        archive.writestr("word/document.xml", '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p/><w:tbl><w:tr><w:tc><w:p><w:r><w:t>Raw table text</w:t></w:r></w:p></w:tc></w:tr></w:tbl></w:body></w:document>')
    result = parse_docx(buffer.getvalue())
    assert result["paragraphs"] == [{"paragraph_number": 2, "text": "Raw table text"}]
