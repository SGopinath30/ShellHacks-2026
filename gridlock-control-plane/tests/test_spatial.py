from app.models import PointGeometry, LineGeometry
from app.spatial import distance_miles, within_threshold


def test_point_to_point_known_distance():
    # Atlanta-ish to a point ~10 miles east
    a = PointGeometry(coordinates=(-84.388, 33.749))
    b = PointGeometry(coordinates=(-84.24, 33.749))
    d = distance_miles(a, b)
    assert 8.0 < d < 10.0  # rough sanity bound, not exact


def test_point_to_point_zero_distance():
    a = PointGeometry(coordinates=(-84.388, 33.749))
    assert distance_miles(a, a) == 0.0


def test_missing_geometry_returns_none():
    a = PointGeometry(coordinates=(-84.388, 33.749))
    assert distance_miles(a, None) is None
    assert distance_miles(None, None) is None


def test_within_threshold_true_and_false():
    a = PointGeometry(coordinates=(-84.388, 33.749))
    b = PointGeometry(coordinates=(-84.24, 33.749))
    assert within_threshold(a, b, threshold_miles=25) is True
    assert within_threshold(a, b, threshold_miles=1) is False


def test_point_to_line():
    point = PointGeometry(coordinates=(-84.30, 33.749))
    line = LineGeometry(coordinates=[(-84.388, 33.749), (-84.20, 33.80)])
    d = distance_miles(point, line)
    assert d is not None
    assert d >= 0


def test_line_to_line():
    line_a = LineGeometry(coordinates=[(-84.388, 33.749), (-84.30, 33.80)])
    line_b = LineGeometry(coordinates=[(-84.20, 33.90), (-84.10, 33.95)])
    d = distance_miles(line_a, line_b)
    assert d is not None
    assert d > 0
