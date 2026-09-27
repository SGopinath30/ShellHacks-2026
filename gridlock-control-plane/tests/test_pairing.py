from datetime import date

from app.matching import compute_matches, eligible_pairs, evaluate_pair
from app.models import (
    PointGeometry,
    ProjectRecord,
    ProjectStatus,
    ProjectType,
    ReasonCode,
    SourceEvidence,
)


def make_project(
    project_id,
    utility_id,
    lon,
    lat,
    start,
    end,
    status=ProjectStatus.PLANNED,
    voltage_kv=230,
):
    return ProjectRecord(
        project_id=project_id,
        utility_id=utility_id,
        project_name=f"{project_id} project",
        project_type=ProjectType.TRANSMISSION_LINE,
        voltage_kv=voltage_kv,
        start_date=start,
        end_date=end,
        status=status,
        geometry=PointGeometry(coordinates=(lon, lat)),
        location_text="test location",
        evidence=SourceEvidence(source_id="src-1", source_name="Test Plan", page_or_row="page 1"),
    )


def test_same_utility_excluded():
    a = make_project("A-1", "UTIL-A", -84.388, 33.749, date(2028, 1, 1), date(2029, 1, 1))
    b = make_project("A-2", "UTIL-A", -84.389, 33.750, date(2028, 1, 1), date(2029, 1, 1))
    assert eligible_pairs([a, b]) == []


def test_different_utility_eligible():
    a = make_project("A-1", "UTIL-A", -84.388, 33.749, date(2028, 1, 1), date(2029, 1, 1))
    b = make_project("B-1", "UTIL-B", -84.389, 33.750, date(2028, 1, 1), date(2029, 1, 1))
    pairs = eligible_pairs([a, b])
    assert len(pairs) == 1


def test_cancelled_project_excluded():
    a = make_project("A-1", "UTIL-A", -84.388, 33.749, date(2028, 1, 1), date(2029, 1, 1))
    b = make_project(
        "B-1", "UTIL-B", -84.389, 33.750, date(2028, 1, 1), date(2029, 1, 1), status=ProjectStatus.CANCELLED
    )
    assert eligible_pairs([a, b]) == []


def test_flag_on_spatial_only():
    a = make_project("A-1", "UTIL-A", -84.388, 33.749, date(2020, 1, 1), date(2020, 6, 1))
    b = make_project("B-1", "UTIL-B", -84.389, 33.750, date(2029, 1, 1), date(2029, 6, 1))
    match = evaluate_pair(a, b, spatial_threshold_miles=25, temporal_min_overlap_days=90)
    assert match is not None
    assert ReasonCode.SPATIAL in match.reason_codes
    assert ReasonCode.TEMPORAL not in match.reason_codes


def test_flag_on_temporal_only():
    a = make_project("A-1", "UTIL-A", -84.388, 33.749, date(2028, 1, 1), date(2029, 1, 1))
    b = make_project("B-1", "UTIL-B", 0.0, 0.0, date(2028, 1, 1), date(2029, 1, 1))  # far away
    match = evaluate_pair(a, b, spatial_threshold_miles=25, temporal_min_overlap_days=90)
    assert match is not None
    assert ReasonCode.TEMPORAL in match.reason_codes
    assert ReasonCode.SPATIAL not in match.reason_codes


def test_no_flag_when_neither_matches():
    a = make_project("A-1", "UTIL-A", -84.388, 33.749, date(2020, 1, 1), date(2020, 6, 1))
    b = make_project("B-1", "UTIL-B", 0.0, 0.0, date(2029, 1, 1), date(2029, 6, 1))
    match = evaluate_pair(a, b, spatial_threshold_miles=25, temporal_min_overlap_days=90)
    assert match is None


def test_similar_voltage_reason_code():
    a = make_project("A-1", "UTIL-A", -84.388, 33.749, date(2028, 1, 1), date(2029, 1, 1), voltage_kv=230)
    b = make_project("B-1", "UTIL-B", -84.389, 33.750, date(2028, 1, 1), date(2029, 1, 1), voltage_kv=230)
    match = evaluate_pair(a, b, spatial_threshold_miles=25, temporal_min_overlap_days=90)
    assert ReasonCode.SIMILAR_VOLTAGE in match.reason_codes


def test_seam_reason_code_when_within_buffer():
    a = make_project("A-1", "UTIL-A", -84.388, 33.749, date(2028, 1, 1), date(2029, 1, 1))
    b = make_project("B-1", "UTIL-B", -84.389, 33.750, date(2028, 1, 1), date(2029, 1, 1))
    match = evaluate_pair(
        a,
        b,
        spatial_threshold_miles=25,
        temporal_min_overlap_days=90,
        seam_buffer_miles=20,
        boundary_distance_miles=5.0,
    )
    assert match.near_boundary is True
    assert ReasonCode.SEAM in match.reason_codes


def test_compute_matches_end_to_end():
    a = make_project("A-1", "UTIL-A", -84.388, 33.749, date(2028, 1, 1), date(2029, 1, 1))
    b = make_project("B-1", "UTIL-B", -84.389, 33.750, date(2028, 1, 1), date(2029, 1, 1))
    # Same utility as A-1 (excluded from pairing with it) AND neither near nor
    # temporally overlapping with B-1, so it should produce no matches at all.
    c = make_project("A-2", "UTIL-A", 0.0, 0.0, date(2015, 1, 1), date(2015, 6, 1))
    matches = compute_matches([a, b, c], spatial_threshold_miles=25, temporal_min_overlap_days=90)
    assert len(matches) == 1
    assert {matches[0].project_a, matches[0].project_b} == {"A-1", "B-1"}


def test_reproducibility_same_inputs_same_result():
    a = make_project("A-1", "UTIL-A", -84.388, 33.749, date(2028, 1, 1), date(2029, 1, 1))
    b = make_project("B-1", "UTIL-B", -84.389, 33.750, date(2028, 1, 1), date(2029, 1, 1))
    m1 = compute_matches([a, b], spatial_threshold_miles=25, temporal_min_overlap_days=90)
    m2 = compute_matches([a, b], spatial_threshold_miles=25, temporal_min_overlap_days=90)
    assert m1[0].distance_miles == m2[0].distance_miles
    assert m1[0].overlap_days == m2[0].overlap_days
    assert m1[0].reason_codes == m2[0].reason_codes
