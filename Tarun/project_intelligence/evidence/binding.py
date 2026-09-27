"""Rules for binding source quotations to a project and attribute."""

from __future__ import annotations

import re

from project_intelligence.contracts import AssociationState


def assess_text_association(
    *,
    project_name: str,
    field_value: object,
    quoted_text: str,
    attribute_cues: tuple[str, ...],
) -> AssociationState:
    normalized_quote = _normalize(quoted_text)
    normalized_name = _normalize(project_name)
    normalized_value = _normalize(str(getattr(field_value, "value", field_value)))
    project_present = normalized_name in normalized_quote
    value_present = normalized_value.replace("_", " ") in normalized_quote
    cue_present = any(_normalize(cue) in normalized_quote for cue in attribute_cues)
    if project_present and value_present and cue_present:
        return AssociationState.ASSOCIATION_VERIFIED
    if value_present and (project_present or cue_present):
        return AssociationState.ASSOCIATION_AMBIGUOUS
    return AssociationState.ASSOCIATION_FAILED


def assess_table_row_association(
    *,
    project_cell: str,
    expected_project_name: str,
    value_cell: str,
    expected_value: object,
) -> AssociationState:
    project_matches = _normalize(project_cell) == _normalize(expected_project_name)
    normalized_expected = _normalize(str(getattr(expected_value, "value", expected_value)))
    value_matches = normalized_expected.replace("_", " ") in _normalize(value_cell)
    return (
        AssociationState.ASSOCIATION_VERIFIED
        if project_matches and value_matches
        else AssociationState.ASSOCIATION_FAILED
    )


def _normalize(value: str) -> str:
    return re.sub(r"[^a-z0-9.]+", " ", value.casefold()).strip()
