from datetime import date

from app.temporal import overlap_days, meets_minimum_overlap


def test_full_overlap():
    a_start, a_end = date(2028, 1, 1), date(2028, 12, 31)
    b_start, b_end = date(2028, 1, 1), date(2028, 12, 31)
    assert overlap_days(a_start, a_end, b_start, b_end) == 365


def test_partial_overlap():
    a_start, a_end = date(2028, 3, 1), date(2029, 8, 31)
    b_start, b_end = date(2028, 10, 1), date(2030, 6, 1)
    days = overlap_days(a_start, a_end, b_start, b_end)
    assert days == (date(2029, 8, 31) - date(2028, 10, 1)).days


def test_one_contained_inside_other():
    a_start, a_end = date(2028, 1, 1), date(2030, 1, 1)
    b_start, b_end = date(2028, 6, 1), date(2028, 9, 1)
    days = overlap_days(a_start, a_end, b_start, b_end)
    assert days == (b_end - b_start).days


def test_same_day_boundary():
    a_start, a_end = date(2028, 1, 1), date(2028, 6, 1)
    b_start, b_end = date(2028, 6, 1), date(2028, 12, 1)
    assert overlap_days(a_start, a_end, b_start, b_end) == 0


def test_no_overlap():
    a_start, a_end = date(2028, 1, 1), date(2028, 6, 1)
    b_start, b_end = date(2029, 1, 1), date(2029, 6, 1)
    assert overlap_days(a_start, a_end, b_start, b_end) == 0


def test_missing_date_returns_none_not_zero():
    a_start, a_end = date(2028, 1, 1), None
    b_start, b_end = date(2028, 6, 1), date(2028, 12, 1)
    assert overlap_days(a_start, a_end, b_start, b_end) is None


def test_meets_minimum_overlap():
    a_start, a_end = date(2028, 3, 1), date(2029, 8, 31)
    b_start, b_end = date(2028, 10, 1), date(2030, 6, 1)
    assert meets_minimum_overlap(a_start, a_end, b_start, b_end, minimum_days=90) is True
    assert meets_minimum_overlap(a_start, a_end, b_start, b_end, minimum_days=10_000) is False


def test_meets_minimum_overlap_missing_date_is_false():
    assert meets_minimum_overlap(None, None, date(2028, 1, 1), date(2028, 6, 1), minimum_days=1) is False
