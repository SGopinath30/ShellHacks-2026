import hashlib
import json
from pathlib import Path

import pytest

from project_intelligence.contracts import (
    ProjectType,
    ProjectValidationOutcome,
    ScheduleType,
    SourceAccess,
    VerificationState,
)
from project_intelligence.extraction.dell_handoff import (
    convert_dell_handoff,
    write_canonical_candidates,
)


def _package(tmp_path: Path, *, access_class: str = "PUBLIC_ASSUMED") -> Path:
    package_id = "PKG-test-handoff"
    package = tmp_path / package_id
    raw_path = package / "raw" / "starter.xlsx"
    raw_path.parent.mkdir(parents=True)
    raw_path.write_bytes(b"preserved workbook bytes")
    source_version_id = "SV-starter"
    common = {
        "association_status": "UNVERIFIED",
        "currentness": "UNVERIFIED_CURRENTNESS",
        "data_label": "STARTER_DATA",
        "source_version_id": source_version_id,
        "source_locator": {"sheet": "projects", "row_number": 2},
        "utility": "DESC",
        "utility_raw": "Dominion Energy South Carolina",
        "state_raw": "SC",
        "synthetic": False,
    }
    seeds = [
        {
            **common,
            "project_candidate_id": "CP-one",
            "starter_id": "DESC_1",
            "project_name": (
                "Stevens Creek - Hooks 115 kV / LR Plumb Branch 46 kV Rebuilds"
            ),
            "endpoint_name_a": "Stevens Creek Sub",
            "endpoint_name_b": "Hooks Sub",
            "raw_in_service_date": "12/31/2024",
        },
        {
            **common,
            "project_candidate_id": "CP-two",
            "starter_id": "GPC_1",
            "utility": "GPC",
            "utility_raw": "Georgia Power",
            "state_raw": "GA",
            "source_locator": {"sheet": "projects", "row_number": 3},
            "project_name": "EVANS - THURMOND DAM #5 115KV REBUILD",
            "endpoint_name_a": "EVANS",
            "endpoint_name_b": "THURMOND DAM #5",
            "raw_in_service_date": "2025-06-01T00:00:00",
        },
    ]
    source = {
        "source_version_id": source_version_id,
        "source_id": "STARTER-PROJECTS",
        "access_class": access_class,
        "raw_path": "raw/starter.xlsx",
        "sha256": hashlib.sha256(raw_path.read_bytes()).hexdigest(),
    }
    manifest = {
        "schema_version": "0.1.0",
        "package_id": package_id,
        "source_records": [source],
        "project_seeds": seeds,
        "geometry_candidates": [],
    }
    (package / "mac_handoff.json").write_text(json.dumps(manifest))
    return package


def test_dell_handoff_converts_starter_rows_to_canonical_candidates(tmp_path) -> None:
    candidates = convert_dell_handoff(_package(tmp_path))

    assert len(candidates) == 2
    first, second = candidates
    assert first.starter_project_id == "DESC_1"
    assert first.source_access is SourceAccess.UNKNOWN
    assert first.voltage_kv.value is None
    assert first.voltage_kv.state is VerificationState.UNRESOLVED
    assert first.project_type.value is ProjectType.TRANSMISSION_LINE
    assert first.schedule.type is ScheduleType.IN_SERVICE_MILESTONE
    assert second.voltage_kv.value == 115
    assert second.schedule.date.isoformat() == "2025-06-01"
    assert all(candidate.field_evidence for candidate in candidates)


def test_dell_handoff_output_includes_validation_and_count(tmp_path) -> None:
    package = _package(tmp_path)
    output = tmp_path / "canonical.json"

    write_canonical_candidates(package, output)

    payload = json.loads(output.read_text())
    assert payload["candidate_count"] == 2
    assert {
        result["outcome"] for result in payload["validation"]
    } == {ProjectValidationOutcome.NEEDS_REVIEW.value}


def test_dell_handoff_rejects_tampered_source_bytes(tmp_path) -> None:
    package = _package(tmp_path)
    (package / "raw" / "starter.xlsx").write_bytes(b"tampered")

    with pytest.raises(ValueError, match="source hash mismatch"):
        convert_dell_handoff(package)
