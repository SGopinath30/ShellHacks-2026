"""Canonical project-status mappings."""

from __future__ import annotations

import re

from project_intelligence.contracts import CanonicalProjectStatus


STATUS_ALIASES = {
    "proposed": CanonicalProjectStatus.PROPOSED,
    "planning": CanonicalProjectStatus.PLANNED,
    "planned": CanonicalProjectStatus.PLANNED,
    "approved": CanonicalProjectStatus.APPROVED,
    "under construction": CanonicalProjectStatus.IN_PROGRESS,
    "construction": CanonicalProjectStatus.IN_PROGRESS,
    "in progress": CanonicalProjectStatus.IN_PROGRESS,
    "delayed": CanonicalProjectStatus.DELAYED,
    "complete": CanonicalProjectStatus.COMPLETED,
    "completed": CanonicalProjectStatus.COMPLETED,
    "cancelled": CanonicalProjectStatus.CANCELLED,
    "canceled": CanonicalProjectStatus.CANCELLED,
    "retired": CanonicalProjectStatus.RETIRED,
}


def normalize_status(value: object) -> CanonicalProjectStatus:
    normalized = re.sub(r"[_-]+", " ", str(value).strip().casefold())
    normalized = re.sub(r"\s+", " ", normalized)
    return STATUS_ALIASES.get(normalized, CanonicalProjectStatus.UNKNOWN)
