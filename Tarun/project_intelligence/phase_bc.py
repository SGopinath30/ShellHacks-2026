"""Deterministic Phase B source reconciliation and Phase C geometry review."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import zipfile
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

from pydantic import TypeAdapter

from project_intelligence.contracts import (
    AssociationState,
    CandidateProject,
    CanonicalProjectStatus,
    EvidenceLocator,
    EvidenceValue,
    ExtractionMethod,
    FieldEvidence,
    GeometryCandidate,
    GeometryOrigin,
    GeometryQuality,
    ProjectType,
    SourceAccess,
    VerificationState,
    VersionState,
)
from project_intelligence.geometry_validation import validate_geometry_candidate
from project_intelligence.normalization.projects import normalize_project_name
from project_intelligence.normalization.schedules import normalize_schedule
from project_intelligence.normalization.status import normalize_status
from project_intelligence.normalization.voltage import extract_voltages_kv
from project_intelligence.reconciliation import compare_versions, reconcile_projects
from project_intelligence.validation import validate_candidate


DESC_PROJECTS_URL = (
    "https://www.scrtp.com/assets/pdfs/home/"
    "2025-2029-2million-and-above-project-descriptions.pdf"
)
DESC_IRP_URL = (
    "https://dms.psc.sc.gov/Attachments/Matter/"
    "8f3cca6c-1724-4a97-b7d4-4194c09cd77c"
)
DESC_JASPER_UPDATE_URL = (
    "https://dms.psc.sc.gov/Attachments/Matter/"
    "f3487fd5-e4cd-46a6-b02f-205db35134aa"
)
GPC_IRP_REGISTRY_URL = (
    "https://psc.ga.gov/search/facts-document/?documentId=221233"
)


@dataclass(frozen=True)
class PublicSource:
    source_version_id: str
    utility_id: str
    title: str
    publisher: str
    path: Path
    source_url: str
    sha256: str
    publication_date: str
    access_basis: str
    evidence_path: Path | None = None
    official_package_path: Path | None = None
    official_package_member: str | None = None

    def manifest(self) -> dict[str, Any]:
        manifest = {
            "source_version_id": self.source_version_id,
            "utility_id": self.utility_id,
            "title": self.title,
            "publisher": self.publisher,
            "path": str(self.path),
            "source_url": self.source_url,
            "sha256": self.sha256,
            "publication_date": self.publication_date,
            "source_access": SourceAccess.PUBLIC.value,
            "access_basis": self.access_basis,
        }
        if self.official_package_path:
            manifest["official_package_path"] = str(self.official_package_path)
            manifest["official_package_sha256"] = _sha256(
                self.official_package_path
            )
            manifest["official_package_member"] = self.official_package_member
        return manifest


@dataclass(frozen=True)
class SourceProject:
    source: PublicSource
    page: int
    name: str
    original_text: str
    external_project_id: str | None = None
    description: str | None = None
    status_raw: str | None = None
    schedule_raw: str | None = None
    schedule_label: str | None = None


def run_phase_b(
    package_dir: str | Path,
    phase_a_path: str | Path,
    current_sources_dir: str | Path,
) -> dict[str, Any]:
    package_dir = Path(package_dir)
    phase_a = _load_candidates(phase_a_path)
    sources = _register_sources(package_dir, Path(current_sources_dir))
    desc_planned = parse_desc_planned_projects(
        _pdf_pages(sources["desc_projects"].path), sources["desc_projects"]
    )
    desc_completed = parse_desc_completed_projects(
        _pdf_pages(sources["desc_irp"].path), sources["desc_irp"]
    )
    desc_updates = parse_desc_update_letters(
        _pdf_pages(sources["desc_jasper_update"].path),
        sources["desc_jasper_update"],
    )
    gpc_projects = parse_gpc_projects(
        _evidence_pages(sources["gpc_irp"].evidence_path), sources["gpc_irp"]
    )
    records_by_utility = {
        "DESC": [*desc_planned, *desc_completed],
        "GPC": gpc_projects,
    }
    supplements_by_utility = {"DESC": desc_updates, "GPC": []}
    verifications = []
    current_candidates = []
    for starter in phase_a:
        records = records_by_utility.get(starter.utility_id, [])
        source_record, score = _best_source_match(starter, records)
        if source_record is None:
            verifications.append(
                {
                    "starter_project_id": starter.starter_project_id,
                    "starter_candidate_id": starter.candidate_project_id,
                    "result": "UNRESOLVED",
                    "reason": "no unique current public-source project match",
                }
            )
            continue
        supplement, supplement_score = _best_source_match(
            starter,
            supplements_by_utility.get(starter.utility_id, []),
            minimum_score=0.45,
        )
        current = build_current_candidate(
            starter,
            source_record,
            supplement if supplement_score >= 0.45 else None,
        )
        comparison = compare_versions(starter, current)
        reconciliation = reconcile_projects(starter, current)
        validation = validate_candidate(current)
        current_candidates.append(current)
        verifications.append(
            {
                "starter_project_id": starter.starter_project_id,
                "starter_candidate_id": starter.candidate_project_id,
                "current_candidate_id": current.candidate_project_id,
                "source_match_score": round(score, 6),
                "result": comparison.result.value,
                "changed_fields": comparison.changed_fields,
                "unresolved_fields": comparison.unresolved_fields,
                "reconciliation": reconciliation.model_dump(mode="json"),
                "validation": validation.model_dump(mode="json"),
                "source_version_ids": [
                    current.source_version_id,
                    *current.supporting_source_version_ids,
                ],
            }
        )
    return {
        "phase": "B",
        "source_policy": (
            "Only official public-disclosure bytes were parsed locally; "
            "no source content was sent to remote inference."
        ),
        "sources": [source.manifest() for source in sources.values()],
        "starter_count": len(phase_a),
        "matched_count": len(current_candidates),
        "current_candidates": [
            candidate.model_dump(mode="json") for candidate in current_candidates
        ],
        "verifications": verifications,
    }


def run_phase_c(
    package_dir: str | Path,
    phase_a_path: str | Path,
    phase_b: dict[str, Any],
) -> dict[str, Any]:
    package_dir = Path(package_dir)
    phase_a = _load_candidates(phase_a_path)
    current_by_id = {
        candidate.candidate_project_id: candidate
        for candidate in TypeAdapter(list[CandidateProject]).validate_python(
            phase_b["current_candidates"]
        )
    }
    current = {
        verification["starter_project_id"]: current_by_id[
            verification["current_candidate_id"]
        ]
        for verification in phase_b["verifications"]
        if verification.get("current_candidate_id") in current_by_id
    }
    starter_by_dell_id = {
        candidate.candidate_project_id: candidate for candidate in phase_a
    }
    raw_candidates = _read_json(package_dir / "geometry_candidates.json")
    results = []
    for raw in raw_candidates:
        if raw.get("provider") != "OPENSTREETMAP":
            continue
        starter = starter_by_dell_id.get(raw.get("project_candidate_id"))
        if starter is None or starter.starter_project_id not in current:
            results.append(
                {
                    "geometry_candidate_id": raw.get("geometry_candidate_id"),
                    "status": "UNRESOLVED",
                    "reasons": ["linked project has no Phase B public-source match"],
                }
            )
            continue
        project = current[starter.starter_project_id]
        geometry = canonical_geometry_candidate(raw, project.candidate_project_id)
        validation = validate_geometry_candidate(project, geometry)
        results.append(
            {
                "starter_project_id": starter.starter_project_id,
                "project_candidate_id": project.candidate_project_id,
                "dell_project_candidate_id": raw["project_candidate_id"],
                "geometry_source_version_id": raw["source_version_id"],
                "geometry_candidate": geometry.model_dump(mode="json"),
                "validation": validation.model_dump(mode="json"),
            }
        )
    status_counts: dict[str, int] = {}
    for result in results:
        status = result.get("validation", {}).get("status", result.get("status"))
        status_counts[status] = status_counts.get(status, 0) + 1
    return {
        "phase": "C",
        "input_geometry_count": len(raw_candidates),
        "osm_geometry_count": len(results),
        "status_counts": status_counts,
        "geometry_validations": results,
    }


def run_phase_bc(
    package_dir: str | Path,
    phase_a_path: str | Path,
    current_sources_dir: str | Path,
    output_dir: str | Path,
) -> tuple[Path, Path]:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    phase_b = run_phase_b(package_dir, phase_a_path, current_sources_dir)
    phase_c = run_phase_c(package_dir, phase_a_path, phase_b)
    phase_b_path = output_dir / "phase_b_source_verification.json"
    phase_c_path = output_dir / "phase_c_geometry_validation.json"
    _write_json(phase_b_path, phase_b)
    _write_json(phase_c_path, phase_c)
    return phase_b_path, phase_c_path


def parse_desc_planned_projects(
    pages: list[dict[str, Any]], source: PublicSource
) -> list[SourceProject]:
    records = []
    for page in pages:
        text = _clean_pdf_text(page["text"])
        if "Project ID" not in text or "Project Description" not in text:
            continue
        name = _between(text, "5 Year Budget", "Project ID")
        project_id = _between(text, "Project ID", "Project Description")
        description = _between(text, "Project Description", "Project Need")
        status = _between(text, "Project Status", "Planned In-Service Date")
        schedule = _between(text, "Planned In-Service Date", "Estimated Project Cost")
        if not name or not project_id:
            continue
        records.append(
            SourceProject(
                source=source,
                page=page["page_number"],
                name=name,
                external_project_id=project_id,
                description=description,
                status_raw=status,
                schedule_raw=schedule,
                schedule_label="Planned In-Service Date",
                original_text=text,
            )
        )
    return records


def parse_desc_completed_projects(
    pages: list[dict[str, Any]], source: PublicSource
) -> list[SourceProject]:
    records = []
    pattern = re.compile(
        r"(?P<name>(?:[ivx]+\.\s*)?[A-Z][^.]{8,180}?)\s*"
        r"\(Completed and In Service (?P<date>[^)]+)\)\s*\.\s*"
        r"(?P<description>DESC rebuilt this line[^.]*\.)",
        re.I,
    )
    for page in pages:
        text = _clean_pdf_text(page["text"])
        for match in pattern.finditer(text):
            name = re.sub(r"^[ivx]+\.\s*", "", match.group("name"), flags=re.I)
            records.append(
                SourceProject(
                    source=source,
                    page=page["page_number"],
                    name=name,
                    description=match.group("description"),
                    status_raw="Completed",
                    schedule_raw=match.group("date"),
                    schedule_label="In-Service Date",
                    original_text=match.group(0),
                )
            )
    return records


def parse_desc_update_letters(
    pages: list[dict[str, Any]], source: PublicSource
) -> list[SourceProject]:
    text = " ".join(_clean_pdf_text(page["text"]) for page in pages)
    subject = re.search(
        r"Construction and Operation of the (?P<name>Jasper\s*[–-]\s*Okatie.+?)"
        r", and Associated Facilities",
        text,
        re.I,
    )
    schedule = re.search(
        r"estimates the commercial operation date for the facilities to be "
        r"(?P<date>[A-Z][a-z]+ \d{1,2}, \d{4})",
        text,
    )
    if not subject or not schedule:
        return []
    original = text[subject.start() : schedule.end()]
    return [
        SourceProject(
            source=source,
            page=2,
            name=subject.group("name"),
            schedule_raw=schedule.group("date"),
            schedule_label="Commercial Operation Date",
            original_text=original,
        )
    ]


def parse_gpc_projects(
    pages: list[dict[str, Any]], source: PublicSource
) -> list[SourceProject]:
    records = []
    header = re.compile(
        r"(?P<name>[A-Z0-9][A-Z0-9 ()#:/&.\-–]+?)\n"
        r"Teams #\s*(?P<id>\d+)\s*\n"
        r"Need Date\s*(?P<need>\d{2}/\d{2}/\d{4})\s*"
        r"Start Date\s*(?P<start>\d{2}/\d{2}/\d{4})",
    )
    description = re.compile(
        r"\* The ITS Assigned designation is for parity forecast purposes only\s*"
        r"(?P<description>.*?)\s*REDACTED",
        re.S,
    )
    for page in pages:
        text = _normalize_page_lines(page["text"])
        match = header.search(text)
        if not match:
            continue
        detail = description.search(text)
        raw_description = (
            _clean_pdf_text(detail.group("description")) if detail else None
        )
        records.append(
            SourceProject(
                source=source,
                page=page["page_number"],
                name=_clean_pdf_text(match.group("name")),
                external_project_id=match.group("id"),
                description=raw_description,
                schedule_raw=match.group("need"),
                schedule_label="Need Date",
                original_text=_clean_pdf_text(text),
            )
        )
    return records


def build_current_candidate(
    starter: CandidateProject,
    record: SourceProject,
    supplement: SourceProject | None = None,
) -> CandidateProject:
    evidence: list[FieldEvidence] = []
    source_ids = [record.source.source_version_id]
    if supplement and supplement.source.source_version_id not in source_ids:
        source_ids.append(supplement.source.source_version_id)

    def bind(
        field_path: str,
        original_text: str,
        normalized_value: object,
        *,
        source_record: SourceProject = record,
        page: int | None = None,
    ) -> str:
        evidence_id = _evidence_id(
            source_record.source.source_version_id,
            starter.starter_project_id or starter.candidate_project_id,
            field_path,
        )
        evidence.append(
            FieldEvidence(
                evidence_id=evidence_id,
                field_path=field_path,
                source_version_id=source_record.source.source_version_id,
                locator=EvidenceLocator(page=page or source_record.page),
                original_text=original_text,
                normalized_value=normalized_value,
                extraction_method=ExtractionMethod.TEXT_RULE,
                validation_state=VerificationState.VERIFIED_RULE,
                association_state=AssociationState.ASSOCIATION_VERIFIED,
            )
        )
        return evidence_id

    utility_text = (
        "Dominion Energy South Carolina"
        if starter.utility_id == "DESC"
        else "2025 IRP TECHNICAL APPENDIX VOLUME 3 TRANSMISSION PLAN"
    )
    utility_evidence = bind(
        "utility_id",
        utility_text,
        starter.utility_id,
        page=record.page if starter.utility_id == "DESC" else 1,
    )
    name = normalize_project_name(record.name)
    name_evidence = bind("name", record.name, name)
    external_evidence_ids = []
    if record.external_project_id:
        external_evidence_ids.append(
            bind(
                "external_project_id",
                record.external_project_id,
                record.external_project_id,
            )
        )
    description = None
    if record.description:
        description_evidence = bind(
            "description", record.description, record.description
        )
        description = EvidenceValue[str](
            value=record.description,
            raw=record.description,
            state=VerificationState.VERIFIED_RULE,
            evidence_ids=[description_evidence],
        )
    voltages = extract_voltages_kv(record.name)
    voltage = None
    if voltages:
        voltage_evidence = bind(
            "voltage_kv",
            record.name,
            voltages[0] if len(voltages) == 1 else voltages,
        )
        voltage = EvidenceValue[float](
            value=voltages[0] if len(voltages) == 1 else None,
            raw=record.name,
            state=(
                VerificationState.VERIFIED_RULE
                if len(voltages) == 1
                else VerificationState.UNRESOLVED
            ),
            evidence_ids=[voltage_evidence],
        )
    status = None
    if record.status_raw:
        normalized_status = normalize_status(record.status_raw)
        status_evidence = bind("status", record.status_raw, normalized_status.value)
        status = EvidenceValue[CanonicalProjectStatus](
            value=normalized_status,
            raw=record.status_raw,
            state=VerificationState.VERIFIED_RULE,
            evidence_ids=[status_evidence],
        )
    project_type = _project_type(record.name)
    type_evidence = bind("project_type", record.name, project_type.value)
    schedule_record = supplement if supplement and supplement.schedule_raw else record
    schedule = None
    if schedule_record.schedule_raw and schedule_record.schedule_label:
        schedule_evidence = bind(
            "schedule",
            schedule_record.schedule_raw,
            schedule_record.schedule_raw,
            source_record=schedule_record,
        )
        schedule = normalize_schedule(
            schedule_record.schedule_raw,
            label=schedule_record.schedule_label,
            evidence_ids=[schedule_evidence],
        )
    endpoints = []
    for index, starter_endpoint in enumerate(starter.endpoints):
        if not starter_endpoint.value:
            continue
        endpoint_evidence = bind(
            f"endpoints.{index}", record.name, starter_endpoint.value
        )
        endpoints.append(
            EvidenceValue[str](
                value=starter_endpoint.value,
                raw=record.name,
                state=VerificationState.VERIFIED_RULE,
                evidence_ids=[endpoint_evidence],
            )
        )
    state = None
    if starter.state and starter.state.value:
        state_source_text = (
            "Dominion Energy South Carolina"
            if starter.utility_id == "DESC"
            else "Georgia Projects"
        )
        state_evidence = bind(
            "state",
            state_source_text,
            starter.state.value,
            page=record.page if starter.utility_id == "DESC" else 171,
        )
        state = EvidenceValue[str](
            value=starter.state.value,
            raw=state_source_text,
            state=VerificationState.VERIFIED_RULE,
            evidence_ids=[state_evidence],
        )
    seed = (
        f"{record.source.source_version_id}|{starter.starter_project_id}|"
        f"{record.external_project_id or record.name}"
    )
    return CandidateProject(
        candidate_project_id=f"CP-{hashlib.sha256(seed.encode()).hexdigest()[:24]}",
        source_version_id=record.source.source_version_id,
        supporting_source_version_ids=source_ids[1:],
        source_access=SourceAccess.PUBLIC,
        utility_id=starter.utility_id,
        utility_id_evidence_ids=[utility_evidence],
        external_project_id=record.external_project_id,
        external_project_id_evidence_ids=external_evidence_ids,
        name=EvidenceValue[str](
            value=name,
            raw=record.name,
            state=VerificationState.VERIFIED_RULE,
            evidence_ids=[name_evidence],
        ),
        description=description,
        voltage_kv=voltage,
        status=status,
        project_type=EvidenceValue[ProjectType](
            value=project_type,
            raw=record.name,
            state=VerificationState.VERIFIED_RULE,
            evidence_ids=[type_evidence],
        ),
        schedule=schedule,
        endpoints=endpoints,
        state=state,
        field_evidence=evidence,
        version_state=VersionState.CANDIDATE,
    )


def canonical_geometry_candidate(
    raw: dict[str, Any], project_candidate_id: str
) -> GeometryCandidate:
    voltage = _provider_voltage_kv(
        (raw.get("provider_properties") or {}).get("voltage")
        or (raw.get("query_metadata") or {}).get("voltage_raw")
    )
    return GeometryCandidate(
        candidate_geometry_id=raw["geometry_candidate_id"],
        project_candidate_id=project_candidate_id,
        geojson=raw["geometry"],
        candidate_feature_name=raw.get("feature_name"),
        provider=GeometryOrigin.OPENSTREETMAP,
        provider_feature_id=raw.get("provider_feature_id"),
        discovery_method=raw.get("discovery_method") or "OVERPASS",
        quality=GeometryQuality.MEDIUM,
        operator=raw.get("operator_raw"),
        voltage_kv=voltage,
    )


def _register_sources(
    package_dir: Path, current_sources_dir: Path
) -> dict[str, PublicSource]:
    manifest = _read_json(package_dir / "mac_handoff.json")
    gpc_record = next(
        source
        for source in manifest["source_records"]
        if source.get("source_id") == "GPC-2025-IRP-V3"
    )
    gpc_path = package_dir / gpc_record["raw_path"]
    sources = {
        "desc_projects": _public_source(
            "DESC",
            "DESC 2025-2029 planned transmission projects",
            "Dominion Energy South Carolina",
            current_sources_dir / "desc-2025-2029-projects.pdf",
            DESC_PROJECTS_URL,
            "2025",
            "Published by the official South Carolina Regional Transmission Planning site",
        ),
        "desc_irp": _public_source(
            "DESC",
            "DESC 2025 Integrated Resource Plan Update",
            "Dominion Energy South Carolina",
            current_sources_dir / "desc-2025-irp-update.pdf",
            DESC_IRP_URL,
            "2025-03-31",
            "Public filing in South Carolina PSC Docket 2025-9-E",
        ),
        "desc_jasper_update": _public_source(
            "DESC",
            "Jasper-Okatie commercial-operation-date update",
            "Dominion Energy South Carolina",
            current_sources_dir / "desc-jasper-okatie-2025-03-07.pdf",
            DESC_JASPER_UPDATE_URL,
            "2025-03-07",
            "Public filing in South Carolina PSC Docket 2023-115-E",
        ),
        "gpc_irp": PublicSource(
            source_version_id=gpc_record["source_version_id"],
            utility_id="GPC",
            title="Georgia Power 2025 IRP Technical Appendix Volume 3",
            publisher="Georgia Power Company",
            path=gpc_path,
            source_url=GPC_IRP_REGISTRY_URL,
            sha256=gpc_record["sha256"],
            publication_date="2025-01-31",
            access_basis=(
                "Byte-for-byte match to Volume 3 inside official Georgia PSC "
                "public-disclosure filing 221233; redacted copy parsed locally"
            ),
            evidence_path=(
                package_dir
                / "evidence"
                / f"{gpc_record['source_version_id']}.json"
            ),
            official_package_path=(
                current_sources_dir / "gpc-2025-irp-public-disclosure.zip"
            ),
            official_package_member=(
                "Technical Appendix Volume 3 PUBLIC DISCLOSURE/"
                "2025 IRP Volume 3 PUBLIC DISCLOSURE.pdf"
            ),
        ),
    }
    for source in sources.values():
        if not source.path.is_file():
            raise FileNotFoundError(source.path)
        if _sha256(source.path) != source.sha256:
            raise ValueError(f"source hash mismatch: {source.source_version_id}")
        if source.official_package_path:
            if not source.official_package_path.is_file():
                raise FileNotFoundError(source.official_package_path)
            with zipfile.ZipFile(source.official_package_path) as archive:
                official_bytes = archive.read(source.official_package_member)
            if hashlib.sha256(official_bytes).hexdigest() != source.sha256:
                raise ValueError(
                    f"official package member mismatch: {source.source_version_id}"
                )
    return sources


def _public_source(
    utility_id: str,
    title: str,
    publisher: str,
    path: Path,
    source_url: str,
    publication_date: str,
    access_basis: str,
) -> PublicSource:
    if not path.is_file():
        raise FileNotFoundError(path)
    sha256 = _sha256(path)
    return PublicSource(
        source_version_id=f"SV-{hashlib.sha256((source_url + sha256).encode()).hexdigest()[:24]}",
        utility_id=utility_id,
        title=title,
        publisher=publisher,
        path=path,
        source_url=source_url,
        sha256=sha256,
        publication_date=publication_date,
        access_basis=access_basis,
    )


def _best_source_match(
    starter: CandidateProject,
    records: list[SourceProject],
    *,
    minimum_score: float = 0.62,
) -> tuple[SourceProject | None, float]:
    scored = sorted(
        ((_match_score(starter, record), record) for record in records),
        key=lambda item: item[0],
        reverse=True,
    )
    if not scored or scored[0][0] < minimum_score:
        return None, scored[0][0] if scored else 0.0
    if len(scored) > 1 and scored[0][0] - scored[1][0] < 0.025:
        return None, scored[0][0]
    return scored[0][1], scored[0][0]


def _match_score(starter: CandidateProject, record: SourceProject) -> float:
    left = _identity_text(starter.name.value or "")
    right = _identity_text(record.name)
    if left == right:
        return 1.0
    ratio = SequenceMatcher(None, left, right).ratio()
    endpoint_hits = 0
    for endpoint in starter.endpoints:
        endpoint_text = _identity_text(endpoint.value or "")
        endpoint_text = re.sub(r"\b(?:sub|substation|primary)\b", "", endpoint_text)
        endpoint_text = re.sub(r"\s+", " ", endpoint_text).strip()
        if endpoint_text and endpoint_text in right:
            endpoint_hits += 1
    starter_voltages = set(extract_voltages_kv(starter.name.value))
    source_voltages = set(extract_voltages_kv(record.name))
    voltage_score = 0.1 if starter_voltages & source_voltages else 0.0
    return min(1.0, ratio * 0.7 + min(endpoint_hits, 2) * 0.1 + voltage_score)


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


def _provider_voltage_kv(value: object) -> float | None:
    if value in (None, ""):
        return None
    try:
        voltage = float(str(value).split(";")[0])
    except ValueError:
        return None
    if voltage > 2_000:
        voltage /= 1_000
    return voltage if 0 < voltage <= 2_000 else None


def _load_candidates(path: str | Path) -> list[CandidateProject]:
    payload = _read_json(Path(path))
    return TypeAdapter(list[CandidateProject]).validate_python(payload["candidates"])


def _pdf_pages(path: Path) -> list[dict[str, Any]]:
    from pypdf import PdfReader

    reader = PdfReader(path)
    return [
        {"page_number": index, "text": page.extract_text() or ""}
        for index, page in enumerate(reader.pages, 1)
    ]


def _evidence_pages(path: Path | None) -> list[dict[str, Any]]:
    if path is None:
        raise ValueError("parsed evidence path is required")
    payload = _read_json(path)
    return payload["pages"]


def _clean_pdf_text(value: str) -> str:
    value = re.sub(r"\b([A-Z])\s+(?=[a-z])", r"\1", value)
    return re.sub(r"\s+", " ", value).strip()


def _normalize_page_lines(value: str) -> str:
    return "\n".join(re.sub(r"\s+", " ", line).strip() for line in value.splitlines())


def _between(value: str, start: str, end: str) -> str | None:
    match = re.search(re.escape(start) + r"\s*(.*?)\s*" + re.escape(end), value)
    return match.group(1).strip() if match else None


def _identity_text(value: str) -> str:
    value = value.casefold().replace("little river", "lr").replace("plum", "plumb")
    value = re.sub(r"\bfort\b", "ft", value)
    return re.sub(r"[^a-z0-9]+", " ", value).strip()


def _evidence_id(source_version_id: str, starter_id: str, field_path: str) -> str:
    seed = f"{source_version_id}|{starter_id}|{field_path}"
    return f"EV-{hashlib.sha256(seed.encode()).hexdigest()[:14]}"


def _sha256(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _write_json(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("package_dir", type=Path)
    parser.add_argument("--phase-a", type=Path, required=True)
    parser.add_argument("--current-sources", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    phase_b, phase_c = run_phase_bc(
        args.package_dir,
        args.phase_a,
        args.current_sources,
        args.output_dir,
    )
    print(json.dumps({"phase_b": str(phase_b), "phase_c": str(phase_c)}))


if __name__ == "__main__":
    main()
