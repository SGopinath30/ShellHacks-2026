"""
Deterministic temporal engine.

PRD section 13:
    overlap_start = max(A.start_date, B.start_date)
    overlap_end   = min(A.end_date, B.end_date)
    overlap_days  = (overlap_end - overlap_start).days if overlap_end >= overlap_start else 0

Missing dates must never be fabricated -- if either project lacks both a
start and end date, overlap is undefined (None), not zero.
"""

from __future__ import annotations

from datetime import date
from typing import Optional


def overlap_days(
    a_start: Optional[date],
    a_end: Optional[date],
    b_start: Optional[date],
    b_end: Optional[date],
) -> Optional[int]:
    """Returns the number of overlapping days between two intervals, or None
    if either interval doesn't have enough information to compute overlap."""
    if a_start is None or a_end is None or b_start is None or b_end is None:
        return None

    overlap_start = max(a_start, b_start)
    overlap_end = min(a_end, b_end)

    if overlap_end >= overlap_start:
        return (overlap_end - overlap_start).days
    return 0


def meets_minimum_overlap(
    a_start: Optional[date],
    a_end: Optional[date],
    b_start: Optional[date],
    b_end: Optional[date],
    minimum_days: int,
) -> bool:
    days = overlap_days(a_start, a_end, b_start, b_end)
    if days is None:
        return False
    return days >= minimum_days
