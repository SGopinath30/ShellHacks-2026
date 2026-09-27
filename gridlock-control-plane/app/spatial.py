"""
Deterministic spatial engine.

PRD section 12: distance must be computed geodesically via PostGIS, between
actual geometries (points or lines) -- never between city-name guesses or
naive Euclidean lat/lon deltas.

This module has two layers:
  1. `distance_miles_sql` / `within_threshold_sql` -- the real PostGIS-backed
     path, used once a Postgres+PostGIS connection is wired up.
  2. `haversine_point_distance_miles` -- a dependency-free pure-Python
     fallback so the matching logic and its tests can run before Postgres is
     available (Phase 1 of the build order explicitly wants no external
     dependency yet). Swap `distance_miles` to call the SQL path once the DB
     is live; the function signature does not change, so callers (matching.py)
     never need to know which implementation is active.
"""

from __future__ import annotations

import math
from typing import Optional

from app.models import Geometry, LineGeometry, PointGeometry

EARTH_RADIUS_MILES = 3958.8


# ---------------------------------------------------------------------------
# Pure-Python fallback (no DB required) -- used until PostGIS is wired up
# ---------------------------------------------------------------------------

def _haversine_miles(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = (
        math.sin(dphi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return EARTH_RADIUS_MILES * c


def _point_to_segment_miles(p, a, b) -> float:
    """Approximate min distance from point p to segment a-b by sampling.
    Good enough for MVP fallback; PostGIS ST_Distance replaces this in prod."""
    steps = 50
    best = math.inf
    for i in range(steps + 1):
        t = i / steps
        lon = a[0] + (b[0] - a[0]) * t
        lat = a[1] + (b[1] - a[1]) * t
        d = _haversine_miles(p[0], p[1], lon, lat)
        best = min(best, d)
    return best


def _line_to_line_miles(line_a: list[tuple[float, float]], line_b: list[tuple[float, float]]) -> float:
    best = math.inf
    for pt in line_a:
        for i in range(len(line_b) - 1):
            best = min(best, _point_to_segment_miles(pt, line_b[i], line_b[i + 1]))
    for pt in line_b:
        for i in range(len(line_a) - 1):
            best = min(best, _point_to_segment_miles(pt, line_a[i], line_a[i + 1]))
    return best


def distance_miles(geom_a: Optional[Geometry], geom_b: Optional[Geometry]) -> Optional[float]:
    """Minimum geodesic distance in miles between two geometries.
    Returns None if either geometry is missing (never fabricate a distance)."""
    if geom_a is None or geom_b is None:
        return None

    if isinstance(geom_a, PointGeometry) and isinstance(geom_b, PointGeometry):
        lon1, lat1 = geom_a.coordinates
        lon2, lat2 = geom_b.coordinates
        return round(_haversine_miles(lon1, lat1, lon2, lat2), 3)

    if isinstance(geom_a, PointGeometry) and isinstance(geom_b, LineGeometry):
        return round(
            min(
                _point_to_segment_miles(geom_a.coordinates, geom_b.coordinates[i], geom_b.coordinates[i + 1])
                for i in range(len(geom_b.coordinates) - 1)
            ),
            3,
        )

    if isinstance(geom_a, LineGeometry) and isinstance(geom_b, PointGeometry):
        return distance_miles(geom_b, geom_a)

    if isinstance(geom_a, LineGeometry) and isinstance(geom_b, LineGeometry):
        return round(_line_to_line_miles(geom_a.coordinates, geom_b.coordinates), 3)

    return None


def within_threshold(geom_a: Optional[Geometry], geom_b: Optional[Geometry], threshold_miles: float) -> bool:
    d = distance_miles(geom_a, geom_b)
    if d is None:
        return False
    return d <= threshold_miles


# ---------------------------------------------------------------------------
# PostGIS SQL path (wire up once app/db.py has a live connection)
# ---------------------------------------------------------------------------

DISTANCE_MILES_SQL = """
SELECT ST_Distance(
    ST_GeomFromGeoJSON(:geom_a)::geography,
    ST_GeomFromGeoJSON(:geom_b)::geography
) / 1609.34 AS distance_miles;
"""

WITHIN_THRESHOLD_SQL = """
SELECT ST_DWithin(
    ST_GeomFromGeoJSON(:geom_a)::geography,
    ST_GeomFromGeoJSON(:geom_b)::geography,
    :threshold_meters
) AS within_threshold;
"""


async def distance_miles_sql(conn, geom_a_geojson: str, geom_b_geojson: str) -> Optional[float]:
    """Real PostGIS path. `conn` is an asyncpg/databases connection.
    Wire this in once db.py exposes a pool, then swap `distance_miles`
    callers in matching.py over to this."""
    row = await conn.fetch_one(
        DISTANCE_MILES_SQL, {"geom_a": geom_a_geojson, "geom_b": geom_b_geojson}
    )
    return row["distance_miles"] if row else None
