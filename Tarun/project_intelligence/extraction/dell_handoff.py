"""Convert Dell's preserved starter handoff into canonical Mac candidates."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any

from project_intelligence.contracts import (
    AssociationState,
    CandidateProject,
    EvidenceLocator,
    EvidenceValue,
    ExtractionMethod,
    FieldEvidence,
    ProjectType,
    SourceAccess,
    VerificationState,
    VersionState,
)
from project_intelligence.normalization.projects import normalize_project_name
from project_intelligence.normalization.schedules import normalize_schedule
from project_intelligence.normalization.voltage import extract_voltages_kv
from project_intelligence.validation import validate_candidate


CANONICAL_HANDOFF_SCHEMA_VERSION = "project-intelligence-candidates-1.0.0"


def convert_dell_handoff(package_dir: str | Path) -> list[CandidateProject]:
    package_path = Path(package_dir)
    manifest = _read_json(package_path / "mac_handoff.json")
    _verify_package(package_path, manifest)
    source_records = {
        record["source_version_id"]: record
        for record in manifest.get("source_records", [])
    }
    candidates = [
        _convert_seed(seed, source_records)
        for seed in manifest.get("project_seeds", [])
    ]
    candidate_ids = {candidate.candidate_project_id for candidate in candidates}
    if len(candidate_ids) != len(candidates):
        raise ValueError("Dell handoff contains duplicate project candidate IDs")
    if not candidates:
        raise ValueError("Dell handoff contains no project seeds")
    return candidates


def write_canonical_candidates(
    package_dir: str | Path,
    output_path: str | Path,
) -> Path:
    package_path = Path(package_dir)
    manifest = _read_json(package_path / "mac_handoff.json")
    candidates = convert_dell_handoff(package_path)
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": CANONICAL_HANDOFF_SCHEMA_VERSION,
        "source_package_id": manifest["package_id"],
        "candidate_count": len(candidates),
        "candidates": [candidate.model_dump(mode="json") for candidate in candidates],
        "validation": [
            validate_candidate(candidate).model_dump(mode="json")
            for candidate in candidates
        ],
    }
    output.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return output


def _convert_seed(
    seed: dict[str, Any],
    source_records: dict[str, dict[str, Any]],
) -> CandidateProject:
    required = (
        "project_candidate_id",
        "source_version_id",
        "starter_id",
        "utility",
        "project_name",
        "source_locator",
    )
    missing = [key for key in required if seed.get(key) in (None, "")]
    if missing:
        raise ValueError(f"Dell project seed is missing required fields: {missing}")
    source_version_id = str(seed["source_version_id"])
    source = source_records.get(source_version_id)
    if source is None:
        raise ValueError(f"missing source record for {source_version_id}")
    source_access = _source_access(source.get("access_class"))
    sheet = str(seed["source_locator"].get("sheet") or "projects")
    row = int(seed["source_locator"]["row_number"])
    evidence: list[FieldEvidence] = []

    def bind(
        field_path: str,
        raw_value: object,
        normalized_value: object,
        *,
        column: str,
        state: VerificationState = VerificationState.VERIFIED_RULE,
    ) -> str:
        evidence_id = _evidence_id(
            source_version_id,
            str(seed["starter_id"]),
            field_path,
        )
        evidence.append(
            FieldEvidence(
                evidence_id=evidence_id,
                field_path=field_path,
                source_version_id=source_version_id,
                locator=EvidenceLocator(
                    sheet=sheet,
                    row=row,
                    column=column,
                    element_id=f"{sheet}!{row}",
                ),
                original_text=str(raw_value),
                normalized_value=_json_value(normalized_value),
                extraction_method=ExtractionMethod.TABLE_PARSER,
                validation_state=state,
                association_state=AssociationState.ASSOCIATION_VERIFIED,
            )
        )
        return evidence_id

    starter_id = str(seed["starter_id"])
    starter_evidence = bind(
        "starter_project_id",
        starter_id,
        starter_id,
        column="project_id",
    )
    utility = str(seed["utility"])
    utility_raw = seed.get("utility_raw") or utility
    utility_evidence = bind(
        "utility_id",
        utility_raw,
        utility,
        column="utility",
    )
    raw_name = str(seed["project_name"])
    name = normalize_project_name(raw_name)
    name_evidence = bind("name", raw_name, name, column="project_name")

    voltages = extract_voltages_kv(raw_name)
    voltage_value = None
    if voltages:
        voltage_state = (
            VerificationState.VERIFIED_RULE
            if len(voltages) == 1
            else VerificationState.UNRESOLVED
        )
        voltage_evidence = bind(
            "voltage_kv",
            raw_name,
            voltages[0] if len(voltages) == 1 else voltages,
            column="project_name",
            state=voltage_state,
        )
        voltage_value = EvidenceValue[float](
            value=voltages[0] if len(voltages) == 1 else None,
            raw=raw_name,
            state=voltage_state,
            evidence_ids=[voltage_evidence],
        )

    project_type = _project_type(raw_name)
    type_evidence = bind(
        "project_type",
        raw_name,
        project_type.value,
        column="project_name",
    )
    project_type_value = EvidenceValue[ProjectType](
        value=project_type,
        raw=raw_name,
        state=VerificationState.VERIFIED_RULE,
        evidence_ids=[type_evidence],
    )

    schedule = None
    raw_schedule = seed.get("raw_in_service_date")
    if raw_schedule not in (None, ""):
        schedule_evidence = bind(
            "schedule",
            raw_schedule,
            raw_schedule,
            column="in_service_date",
        )
        schedule = normalize_schedule(
            raw_schedule,
            label="in_service_date",
            evidence_ids=[schedule_evidence],
        )

    endpoints = []
    for field_name, column in (
        ("endpoint_name_a", "name_a"),
        ("endpoint_name_b", "name_b"),
    ):
        raw_endpoint = seed.get(field_name)
        if raw_endpoint in (None, ""):
            continue
        endpoint = normalize_project_name(raw_endpoint)
        endpoint_evidence = bind(
            f"endpoints.{len(endpoints)}",
            raw_endpoint,
            endpoint,
            column=column,
        )
        endpoints.append(
            EvidenceValue[str](
                value=endpoint,
                raw=str(raw_endpoint),
                state=VerificationState.VERIFIED_RULE,
                evidence_ids=[endpoint_evidence],
            )
        )

    state_value = None
    raw_state = seed.get("state_raw")
    if raw_state not in (None, ""):
        state_evidence = bind("state", raw_state, raw_state, column="state")
        state_value = EvidenceValue[str](
            value=str(raw_state),
            raw=str(raw_state),
            state=VerificationState.VERIFIED_RULE,
            evidence_ids=[state_evidence],
        )

    return CandidateProject(
        candidate_project_id=str(seed["project_candidate_id"]),
        source_version_id=source_version_id,
        source_access=source_access,
        utility_id=utility,
        utility_id_evidence_ids=[utility_evidence],
        starter_project_id=starter_id,
        starter_project_id_evidence_ids=[starter_evidence],
        name=EvidenceValue[str](
            value=name,
            raw=raw_name,
            state=VerificationState.VERIFIED_RULE,
            evidence_ids=[name_evidence],
        ),
        voltage_kv=voltage_value,
        project_type=project_type_value,
        schedule=schedule,
        endpoints=endpoints,
        state=state_value,
        field_evidence=evidence,
        version_state=VersionState.STARTER_DATA,
    )


def _verify_package(package_dir: Path, manifest: dict[str, Any]) -> None:
    if manifest.get("schema_version") != "0.1.0":
        raise ValueError(f"unsupported Dell handoff schema: {manifest.get('schema_version')}")
    if package_dir.name != manifest.get("package_id"):
        raise ValueError("Dell package directory does not match package_id")
    package_root = package_dir.resolve()
    for source in manifest.get("source_records", []):
        raw_path = (package_dir / source["raw_path"]).resolve()
        if not raw_path.is_relative_to(package_root):
            raise ValueError("source raw_path escapes the Dell package")
        if not raw_path.is_file():
            raise ValueError(f"missing raw source bytes: {source['source_version_id']}")
        actual_hash = hashlib.sha256(raw_path.read_bytes()).hexdigest()
        if actual_hash != source["sha256"]:
            raise ValueError(f"source hash mismatch: {source['source_version_id']}")


def _source_access(access_class: object) -> SourceAccess:
    if access_class == "PUBLIC_CONFIRMED":
        return SourceAccess.PUBLIC
    if access_class == "CEII":
        raise ValueError("CEII sources cannot enter canonical conversion")
    return SourceAccess.UNKNOWN


def _project_type(name: str) -> ProjectType:
    normalized = name.casefold()
    if "reconductor" in normalized:
        return ProjectType.RECONDUCTORING
    if "reactor" in normalized:
        return ProjectType.OTHER
    if any(term in normalized for term in ("rebuild", "construct", "line", "tie")):
        return ProjectType.TRANSMISSION_LINE
    if "substation" in normalized or re.search(r"\bsub\b", normalized):
        return ProjectType.SUBSTATION
    return ProjectType.UNKNOWN


def _evidence_id(source_version_id: str, starter_id: str, field_path: str) -> str:
    seed = f"{source_version_id}|{starter_id}|{field_path}"
    return f"EV-{hashlib.sha256(seed.encode()).hexdigest()[:14]}"


def _json_value(value: object) -> object:
    if hasattr(value, "value"):
        return value.value
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected a JSON object: {path}")
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Convert a Dell mac_handoff package into canonical candidates."
    )
    parser.add_argument("package_dir", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = write_canonical_candidates(args.package_dir, args.output)
    print(output)


if __name__ == "__main__":
    main()
