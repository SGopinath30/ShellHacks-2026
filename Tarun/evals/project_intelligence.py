"""Field-level evaluation for project-intelligence outputs."""

from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass
from enum import StrEnum
from typing import Any, Iterable


class FieldEvaluationCategory(StrEnum):
    CORRECT = "CORRECT"
    ACCEPTABLE_NORMALIZATION = "ACCEPTABLE_NORMALIZATION"
    UNRESOLVED = "UNRESOLVED"
    WRONG = "WRONG"
    UNSUPPORTED_HALLUCINATION = "UNSUPPORTED_HALLUCINATION"


@dataclass(frozen=True)
class ProjectIntelligenceMetrics:
    total_fields: int
    schema_valid_outputs: int
    schema_invalid_outputs: int
    category_counts: dict[str, int]
    exact_field_accuracy: float
    evidence_association_accuracy: float
    unsupported_value_rate: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def evaluate_field_categories(
    categories: Iterable[FieldEvaluationCategory],
    *,
    schema_valid_outputs: int,
    schema_invalid_outputs: int,
    evidence_associations: Iterable[bool],
) -> ProjectIntelligenceMetrics:
    materialized = list(categories)
    associations = list(evidence_associations)
    counts = Counter(materialized)
    total = len(materialized)
    return ProjectIntelligenceMetrics(
        total_fields=total,
        schema_valid_outputs=schema_valid_outputs,
        schema_invalid_outputs=schema_invalid_outputs,
        category_counts={category.value: counts[category] for category in FieldEvaluationCategory},
        exact_field_accuracy=_divide(counts[FieldEvaluationCategory.CORRECT], total),
        evidence_association_accuracy=_divide(sum(associations), len(associations)),
        unsupported_value_rate=_divide(
            counts[FieldEvaluationCategory.UNSUPPORTED_HALLUCINATION], total
        ),
    )


def categorize_field(
    *,
    expected: object,
    actual: object,
    source_supported: bool,
    normalization_equivalent: bool = False,
) -> FieldEvaluationCategory:
    if actual is None:
        return FieldEvaluationCategory.UNRESOLVED
    if not source_supported:
        return FieldEvaluationCategory.UNSUPPORTED_HALLUCINATION
    if actual == expected:
        return FieldEvaluationCategory.CORRECT
    if normalization_equivalent:
        return FieldEvaluationCategory.ACCEPTABLE_NORMALIZATION
    return FieldEvaluationCategory.WRONG


def _divide(numerator: float, denominator: float) -> float:
    return numerator / denominator if denominator else 0.0
