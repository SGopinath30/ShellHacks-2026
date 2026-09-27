"""Persistent project versions and indexed PostGIS candidate search."""
import hashlib
import json
import os
from pathlib import Path
import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from .config import Profile
from .contracts import ProjectVersion, geometry_status
from .engine import center, haversine, opportunity, pair_id


def connect():
    url = os.getenv("DATABASE_URL", "postgresql://gridlock:gridlock@127.0.0.1:55432/synchro")
    return psycopg.connect(url, connect_timeout=3, row_factory=dict_row)


def migrate():
    sql = (Path(__file__).resolve().parents[2] / "db/challenge.sql").read_text()
    with connect() as conn:
        conn.execute(sql)


def health():
    try:
        with connect() as conn:
            version = conn.execute("SELECT PostGIS_Lib_Version() AS version").fetchone()["version"]
            schema = conn.execute("SELECT to_regclass('synchro.project_versions') AS name").fetchone()["name"]
        compatible = tuple(map(int, version.split('.')[:2])) >= (3,4)
        ready = compatible and schema is not None
        return {"status":"ok" if ready else "unavailable", "api":"ok", "database":"ok",
                "postgis":version, "postgis_compatible":compatible, "schema":"ok" if schema else "missing"}
    except psycopg.Error:
        return {"status":"unavailable", "api":"ok", "database":"unavailable", "postgis":"unavailable"}


def save(candidate):
    payload = candidate.model_dump(mode="json")
    digest = hashlib.sha256(json.dumps(payload,sort_keys=True,separators=(",",":")).encode()).hexdigest()[:20]
    with connect() as conn:
        conn.execute("INSERT INTO synchro.utilities VALUES (%s) ON CONFLICT DO NOTHING", (candidate.utility_id,))
        conn.execute("INSERT INTO synchro.projects VALUES (%s,%s) ON CONFLICT DO NOTHING", (candidate.project_id,candidate.utility_id))
        locked = conn.execute("SELECT utility_id FROM synchro.projects WHERE project_id=%s FOR UPDATE", (candidate.project_id,)).fetchone()
        if locked["utility_id"] != candidate.utility_id:
            raise ValueError("A project ID cannot change utilities")
        row = conn.execute("SELECT payload FROM synchro.project_versions WHERE project_id=%s AND is_current", (candidate.project_id,)).fetchone()
        if row:
            current = ProjectVersion.model_validate(row["payload"])
            if current.model_dump(mode="json",exclude={"version_id","version_number"}) == payload:
                return current
        number = conn.execute("SELECT COALESCE(MAX(version_number),0)+1 AS n FROM synchro.project_versions WHERE project_id=%s", (candidate.project_id,)).fetchone()["n"]
        result = ProjectVersion(**payload,version_id=f"PV-{digest}-{number}",version_number=number)
        conn.execute("UPDATE synchro.project_versions SET is_current=false WHERE project_id=%s AND is_current",(candidate.project_id,))
        conn.execute("""INSERT INTO synchro.project_versions
          (version_id,project_id,version_number,payload,geometry,accepted_at)
          VALUES (%s,%s,%s,%s,ST_SetSRID(ST_GeomFromGeoJSON(%s),4326),
                  CASE WHEN %s THEN now() ELSE NULL END)""",
          (result.version_id,result.project_id,number,Jsonb(result.model_dump(mode="json")),
           candidate.geometry.model_dump_json() if candidate.geometry else None,
           candidate.validation_state == "ACCEPTED" and not candidate.is_fixture))
        return result


def projects():
    with connect() as conn:
        rows = conn.execute('SELECT payload FROM synchro.project_versions WHERE is_current ORDER BY project_id COLLATE "C"').fetchall()
    return [ProjectVersion.model_validate(r["payload"]) for r in rows]


def spatial_candidates(conn,config):
    # ST_DWithin uses the geography GiST index; strict upper bound is applied
    # in opportunity() because the sponsor says "under" the threshold.
    return conn.execute("""
        SELECT a.payload AS a,b.payload AS b,
          CASE WHEN ST_Intersects(a.geometry,b.geometry) THEN 0
               ELSE ST_Distance(a.geometry::geography,b.geometry::geography) END AS meters,
          ST_Intersects(a.geometry,b.geometry) AS intersects,
          ST_AsGeoJSON(ST_ClosestPoint(a.geometry::geography,b.geometry::geography)::geometry)::json AS closest_point_a,
          ST_AsGeoJSON(ST_ClosestPoint(b.geometry::geography,a.geometry::geography)::geometry)::json AS closest_point_b
        FROM synchro.project_versions a
        JOIN synchro.project_versions b
          ON a.project_id COLLATE "C" < b.project_id COLLATE "C"
         AND a.payload->>'utility_id' <> b.payload->>'utility_id'
         AND ST_DWithin(a.geometry::geography,b.geometry::geography,%s)
        WHERE a.is_current AND b.is_current AND a.geometry IS NOT NULL AND b.geometry IS NOT NULL
          AND (a.payload->>'status' = ANY(%s) OR a.payload->>'is_fixture' = 'true') AND (b.payload->>'status' = ANY(%s) OR b.payload->>'is_fixture' = 'true')
          AND a.payload->>'validation_state' <> 'UNRESOLVED' AND b.payload->>'validation_state' <> 'UNRESOLVED'
          AND a.payload->>'geometry_quality' <> 'UNRESOLVED' AND b.payload->>'geometry_quality' <> 'UNRESOLVED'
        """,(config.maximum_meters,list(config.eligible_statuses),list(config.eligible_statuses))).fetchall()


def opportunities(config):
    matches = []
    with connect() as conn:
        if config.profile == Profile.CHALLENGE_GEOMETRY:
            candidates = spatial_candidates(conn,config)
        else:
            rows = conn.execute('SELECT payload FROM synchro.project_versions WHERE is_current ORDER BY project_id COLLATE "C"').fetchall()
            grouped = {}
            for row in rows:
                p = ProjectVersion.model_validate(row["payload"])
                if center(p) and geometry_status(p) != "UNAVAILABLE" and (p.status in config.eligible_statuses or p.is_fixture):
                    grouped.setdefault(p.utility_id,[]).append(p)
            candidates = []
            utilities = sorted(grouped)
            for i,u in enumerate(utilities):
                for v in utilities[i+1:]:
                    for x in grouped[u]:
                        for y in grouped[v]:
                            a,b = sorted((x,y),key=lambda p:p.project_id)
                            ca,cb = center(a),center(b)
                            candidates.append({"a":a.model_dump(),"b":b.model_dump(),
                                "meters":haversine(ca.coordinates,cb.coordinates,config),"intersects":False,
                                "closest_point_a":ca.model_dump(),"closest_point_b":cb.model_dump()})
        for row in candidates:
            a,b = ProjectVersion.model_validate(row["a"]),ProjectVersion.model_validate(row["b"])
            result = opportunity(a,b,row,config)
            if result:
                matches.append(result)
                conn.execute("INSERT INTO synchro.project_pairs VALUES (%s,%s,%s) ON CONFLICT DO NOTHING",
                             (pair_id(a.project_id,b.project_id),a.project_id,b.project_id))
    return sorted(matches,key=lambda m:m["rank_key"])
