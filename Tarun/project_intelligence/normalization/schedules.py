"""Schedule semantics and coarse-date normalization."""

from __future__ import annotations

import calendar
import re
from datetime import date, datetime

from project_intelligence.contracts import (
    DatePrecision,
    DateRange,
    Schedule,
    ScheduleType,
    ScheduleValidationOutcome,
    VerificationState,
)


EXACT_DATE_FORMATS = (
    "%m/%d/%Y",
    "%m/%d/%y",
    "%Y-%m-%d",
    "%Y-%m-%dT%H:%M:%S",
    "%B %d, %Y",
    "%b %d, %Y",
)


def classify_schedule_type(label: str) -> ScheduleType:
    normalized = re.sub(r"[_-]+", " ", label.casefold())
    if any(cue in normalized for cue in ("in service", "commercial operation", "cod")):
        return ScheduleType.IN_SERVICE_MILESTONE
    if "need date" in normalized:
        return ScheduleType.NEED_DATE_MILESTONE
    if "construction start" in normalized or normalized.strip() == "start date":
        return ScheduleType.CONSTRUCTION_START_ONLY
    if any(cue in normalized for cue in ("construction end", "completion date")):
        return ScheduleType.CONSTRUCTION_END_ONLY
    return ScheduleType.UNKNOWN


def normalize_schedule(
    value: object,
    *,
    label: str,
    evidence_ids: list[str],
    state: VerificationState = VerificationState.VERIFIED_RULE,
) -> Schedule | None:
    if value is None or value == "":
        return None
    schedule_type = classify_schedule_type(label)
    raw = _raw_schedule(value)
    exact_date = _exact_date(value)
    if exact_date:
        return Schedule(
            type=schedule_type,
            raw=raw,
            date=exact_date,
            precision=DatePrecision.EXACT,
            validation=ScheduleValidationOutcome.VALID,
            state=state,
            evidence_ids=evidence_ids,
        )

    quarter = re.fullmatch(r"Q([1-4])\s+(\d{4})", raw, re.I)
    if quarter:
        quarter_number = int(quarter.group(1))
        year = int(quarter.group(2))
        first_month = (quarter_number - 1) * 3 + 1
        last_month = first_month + 2
        return _range_schedule(
            schedule_type,
            raw,
            DatePrecision.QUARTER,
            date(year, first_month, 1),
            date(year, last_month, calendar.monthrange(year, last_month)[1]),
            evidence_ids,
            state,
        )

    month = re.fullmatch(r"([A-Za-z]+)\s+(\d{4})", raw)
    if month:
        month_number = _month_number(month.group(1))
        if month_number is None:
            return _season_schedule(
                schedule_type,
                raw,
                month.group(1),
                int(month.group(2)),
                evidence_ids,
                state,
            )
        year = int(month.group(2))
        return _range_schedule(
            schedule_type,
            raw,
            DatePrecision.MONTH,
            date(year, month_number, 1),
            date(year, month_number, calendar.monthrange(year, month_number)[1]),
            evidence_ids,
            state,
        )

    year_match = re.fullmatch(r"\d{4}", raw)
    if year_match:
        year = int(raw)
        return _range_schedule(
            schedule_type,
            raw,
            DatePrecision.YEAR,
            date(year, 1, 1),
            date(year, 12, 31),
            evidence_ids,
            state,
        )

    return Schedule(
        type=schedule_type,
        raw=raw,
        precision=DatePrecision.UNKNOWN,
        validation=ScheduleValidationOutcome.PARTIALLY_FEASIBLE,
        state=VerificationState.UNRESOLVED,
        evidence_ids=evidence_ids,
    )


def construction_window(
    *,
    start: DateRange,
    end: DateRange,
    raw: str,
    evidence_ids: list[str],
    state: VerificationState = VerificationState.VERIFIED_RULE,
) -> Schedule:
    return Schedule(
        type=ScheduleType.CONSTRUCTION_WINDOW,
        raw=raw,
        start=start,
        end=end,
        state=state,
        evidence_ids=evidence_ids,
    )


def _raw_schedule(value: object) -> str:
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return str(value).strip()


def _exact_date(value: object) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()
    for date_format in EXACT_DATE_FORMATS:
        try:
            return datetime.strptime(text, date_format).date()
        except ValueError:
            continue
    return None


def _month_number(value: str) -> int | None:
    for date_format in ("%B", "%b"):
        try:
            return datetime.strptime(value, date_format).month
        except ValueError:
            continue
    return None


def _season_schedule(
    schedule_type: ScheduleType,
    raw: str,
    season: str,
    year: int,
    evidence_ids: list[str],
    state: VerificationState,
) -> Schedule:
    normalized = season.casefold()
    bounds = {
        "spring": (date(year, 3, 1), date(year, 5, 31)),
        "summer": (date(year, 6, 1), date(year, 8, 31)),
        "fall": (date(year, 9, 1), date(year, 11, 30)),
        "autumn": (date(year, 9, 1), date(year, 11, 30)),
        "winter": (date(year, 12, 1), date(year + 1, 2, calendar.monthrange(year + 1, 2)[1])),
    }
    if normalized not in bounds:
        return Schedule(
            type=schedule_type,
            raw=raw,
            precision=DatePrecision.UNKNOWN,
            validation=ScheduleValidationOutcome.PARTIALLY_FEASIBLE,
            state=VerificationState.UNRESOLVED,
            evidence_ids=evidence_ids,
        )
    earliest, latest = bounds[normalized]
    return _range_schedule(
        schedule_type,
        raw,
        DatePrecision.SEASON,
        earliest,
        latest,
        evidence_ids,
        state,
    )


def _range_schedule(
    schedule_type: ScheduleType,
    raw: str,
    precision: DatePrecision,
    earliest: date,
    latest: date,
    evidence_ids: list[str],
    state: VerificationState,
) -> Schedule:
    return Schedule(
        type=schedule_type,
        raw=raw,
        range=DateRange(earliest=earliest, latest=latest),
        precision=precision,
        validation=ScheduleValidationOutcome.VALID,
        state=state,
        evidence_ids=evidence_ids,
    )
