"""Detection and field-accuracy metrics for JSONL extraction outputs."""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable


DEFAULT_FIELDS = (
    "utility_id",
    "project_name",
    "project_type",
    "voltage_kv",
    "start_date",
    "end_date",
    "status",
    "location_text",
    "source_id",
    "source_page_row",
)


@dataclass(frozen=True)
class EvaluationMetrics:
    true_positives: int
    false_positives: int
    false_negatives: int
    precision: float
    recall: float
    f1: float
    field_accuracy: float
    matched_projects: int
    fields_scored: int


def load_jsonl(path: str | Path) -> list[dict[str, Any]]:
    rows = []
    with Path(path).open(encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, start=1):
            if not line.strip():
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise ValueError(f"invalid JSON on {path}:{line_number}") from exc
    return rows


def evaluate_files(
    gold_path: str | Path,
    predictions_path: str | Path,
    *,
    fields: Iterable[str] = DEFAULT_FIELDS,
) -> EvaluationMetrics:
    return evaluate_rows(load_jsonl(gold_path), load_jsonl(predictions_path), fields=fields)


def evaluate_rows(
    gold_rows: Iterable[dict[str, Any]],
    prediction_rows: Iterable[dict[str, Any]],
    *,
    fields: Iterable[str] = DEFAULT_FIELDS,
) -> EvaluationMetrics:
    """Score rows shaped as ``{"case_id": ..., "projects": [...]}``.

    Projects match within a case by ``source_project_id`` when present, otherwise
    by a normalized project name.  A match counts toward detection even when one
    or more extracted fields are wrong; those errors appear in field accuracy.
    """

    gold = {row["case_id"]: row.get("projects", []) for row in gold_rows}
    predicted = {row["case_id"]: row.get("projects", []) for row in prediction_rows}
    selected_fields = tuple(fields)
    true_positives = false_positives = false_negatives = 0
    correct_fields = total_fields = matched_projects = 0

    for case_id in gold.keys() | predicted.keys():
        expected_projects = gold.get(case_id, [])
        actual_projects = predicted.get(case_id, [])
        remaining = list(actual_projects)

        for expected in expected_projects:
            expected_key = _project_key(expected)
            match_index = next(
                (
                    index
                    for index, project in enumerate(remaining)
                    if _project_key(project) == expected_key
                ),
                None,
            )
            if match_index is None:
                false_negatives += 1
                continue
            actual = remaining.pop(match_index)
            true_positives += 1
            matched_projects += 1
            for field in selected_fields:
                total_fields += 1
                if _normalized_value(actual.get(field)) == _normalized_value(expected.get(field)):
                    correct_fields += 1
        false_positives += len(remaining)

    precision = _safe_divide(true_positives, true_positives + false_positives)
    recall = _safe_divide(true_positives, true_positives + false_negatives)
    f1 = _safe_divide(2 * precision * recall, precision + recall)
    return EvaluationMetrics(
        true_positives=true_positives,
        false_positives=false_positives,
        false_negatives=false_negatives,
        precision=precision,
        recall=recall,
        f1=f1,
        field_accuracy=_safe_divide(correct_fields, total_fields),
        matched_projects=matched_projects,
        fields_scored=total_fields,
    )


def _project_key(project: dict[str, Any]) -> str:
    source_project_id = project.get("source_project_id")
    if source_project_id:
        return f"id:{str(source_project_id).casefold()}"
    name = str(project.get("project_name") or "")
    return "name:" + re.sub(r"[^a-z0-9]+", "", name.casefold())


def _normalized_value(value: Any) -> Any:
    return value.casefold().strip() if isinstance(value, str) else value


def _safe_divide(numerator: float, denominator: float) -> float:
    return numerator / denominator if denominator else 0.0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("gold", type=Path)
    parser.add_argument("predictions", type=Path)
    args = parser.parse_args()
    print(json.dumps(asdict(evaluate_files(args.gold, args.predictions)), indent=2))


if __name__ == "__main__":
    main()
