# GridLock — Control Plane

Owns `backend/`, `matching/`, `modal/` on branch `feat/control-plane`.

Deterministic spatial + temporal engine, FastAPI, and the Postgres/PostGIS
schema. This is the "decide" half of *"LLMs extract and assist; deterministic
systems decide."* It has zero dependency on Nemotron/Modal/Swarms — it only
needs `ProjectRecord`s, however they got produced.

## Quickstart (no DB required yet)

```bash
conda create -n gridlock python=3.12
conda activate gridlock
pip install -r requirements.txt

# run tests -- deterministic engine works standalone
pytest -v

# run the API with in-memory storage
uvicorn app.main:app --reload
```

Then seed the PRD's demo example (Riverbend / Northgate):

```bash
python -c "from scripts.seed_demo_data import seed; seed()"
```

**Note:** the seed script currently writes to its own in-memory
`Repository` instance, separate from the one the running `uvicorn` process
uses. Data seeded this way won't show up in `GET /projects` on the live
server. Until `seed_demo_data.py` is updated to POST through the API
instead, use the manual verification steps below to get data into the
running server.

or, with the server running, hit `POST /matches/recompute` after posting
projects via `POST /projects`.

Visit `http://localhost:8000/docs` for interactive API docs.

## Verifying it locally

1. Start the server (`uvicorn app.main:app --reload`) and open
   `http://127.0.0.1:8000/docs`.
2. Under `POST /projects` ("Upsert Project"), click **Try it out**, paste in
   a project JSON body, and **Execute**. Repeat for each test project — same
   endpoint, called multiple times, each with a different `project_id`
   (re-POSTing the same `project_id` overwrites/updates that record, since
   this is an upsert).
   - Watch out for enum fields — `start_date_precision` /
     `end_date_precision` only accept `exact`, `quarter`, `year`, or
     `unknown` (not `month`).
   - `geometry.coordinates` must be real numbers `[longitude, latitude]`,
     never `null`.
3. Confirm saved records via `GET /projects` — Try it out, Execute, check
   all expected `project_id`s appear in the response array.
4. Run `POST /matches/recompute` with an explicit body — **the field names
   are `spatial_threshold_miles`, `temporal_min_overlap_days`, and
   `seam_buffer_miles`** (not `temporal_overlap_days` — an unrecognized
   field name is silently dropped and the default `90`-day threshold is
   used instead, which can make a real temporal match look like it's not
   firing). Example:
```json
   {
     "spatial_threshold_miles": 1,
     "temporal_min_overlap_days": 30,
     "seam_buffer_miles": 20
   }
```
5. Check `GET /matches` — verify `reason_codes` reflects the actual
   thresholds: `SPATIAL` requires `distance_miles <= spatial_threshold_miles`,
   `TEMPORAL` requires `overlap_days >= temporal_min_overlap_days`
   (`app/matching.py::evaluate_pair`). A pair can carry both codes, either
   one alone, or neither (in which case it won't appear in results at all —
   `flag = spatial_match OR temporal_match`).
6. **Negative test:** post a project that's far away, non-overlapping in
   dates, and/or shares a `utility_id` with another — confirm it does *not*
   appear in any match after recompute. Proves the engine discriminates
   correctly rather than flagging everything.

### Known-good test fixtures

Three projects that together exercise both spatial-only and temporal-only
matches, depending on the thresholds used:

| project_id       | utility_id  | coordinates (lon, lat)     | dates                     |
|------------------|-------------|-----------------------------|-----------------------------|
| `riverbend-001`  | `utility-a` | `[-81.3792, 28.5383]`      | 2026-11-01 → 2027-02-01     |
| `northgate-002`  | `utility-b` | `[-81.55, 28.7]`           | 2026-12-01 → 2027-03-01     |
| `eastpark-003`   | `utility-c` | `[-81.5, 28.65]`           | 2026-11-15 → 2027-01-15     |

- With `spatial_threshold_miles: 1`, `temporal_min_overlap_days: 90`:
  no pairs are close enough (10–15+ miles apart) and no overlap reaches 90
  days (45–62 days) → **expect an empty match list**.
- With `spatial_threshold_miles: 1`, `temporal_min_overlap_days: 30`:
  still no pairs are within 1 mile, but all three overlaps (45, 61, 62
  days) clear 30 → **expect all three pairs matched, each with
  `reason_codes: ["TEMPORAL"]`**.
- To see a `SPATIAL`-only match, re-POST `northgate-002` with coordinates
  close to `riverbend-001` (e.g. `[-81.385, 28.542]`, ~0.4 miles away) and
  recompute with `spatial_threshold_miles: 1`.

This proves the full vertical slice: ingest → store → deterministic match →
surface, without needing Postgres.

## With Postgres/PostGIS

```bash
docker compose up -d
```

This brings up Postgres+PostGIS on `localhost:5432` (`gridlock`/`gridlock`)
and applies `db/init.sql`. The app still runs against the in-memory
`Repository` in `app/db.py` until that's swapped for a real DB-backed
implementation — the interface is designed so routers don't change when you
do that swap. `app/spatial.py` already has the `ST_Distance` /
`ST_DWithin` SQL ready to go (`distance_miles_sql`).

## Project layout

## Design notes (see PRD for full detail)

- **flag = spatial_match OR temporal_match.** Nothing more clever than that
  for MVP (`app/matching.py::evaluate_pair`).
  - `spatial_match`: `distance_miles <= spatial_threshold_miles`
  - `temporal_match`: `overlap_days >= temporal_min_overlap_days`
  - A match can carry one or both reason codes; nothing is flagged if
    neither condition is met.
- **Never fabricate.** Missing geometry -> `distance_miles` returns `None`,
  never 0. Missing dates -> `overlap_days` returns `None`, never 0.
- **Reproducibility.** `compute_matches` is a pure function of
  (projects, thresholds). Same inputs -> same `MatchResult`s, always
  (`tests/test_pairing.py::test_reproducibility_same_inputs_same_result`).
- **Same-utility pairs are always excluded** before any spatial/temporal
  check runs (`eligible_pairs`).
- **Seams Mode** takes a precomputed boundary distance per pair rather than
  computing it itself — boundary geometry is a separate dataset the
  ingestion side owns; this keeps `matching.py` free of that dependency.

## API surface

| Method | Path                     | Purpose                                   |
|--------|--------------------------|--------------------------------------------|
| POST   | `/sources`               | Register a source doc (stub)              |
| POST   | `/sources/{id}/ingest`   | Trigger extraction (stub)                 |
| GET    | `/projects`              | Query normalized projects                 |
| GET    | `/projects/{id}`         | One project's full record                 |
| POST   | `/projects`              | Upsert a normalized project record        |
| POST   | `/matches/recompute`     | Recalculate every coordination opportunity|
| GET    | `/matches`               | List current matches                      |
| GET    | `/matches/{id}`          | One match's full detail                   |
| POST   | `/matches/{id}/review`   | Set Investigate/Dismiss/Contact Utility   |
| GET    | `/health`                | Health check                               |

`POST /matches/recompute` request body (`MatchRecomputeRequest`):
`spatial_threshold_miles` (float), `temporal_min_overlap_days` (int),
`seam_buffer_miles` (float, optional), `utility_ids` (optional list to
scope recompute to specific utilities). Defaults per `compute_matches`:
`spatial_threshold_miles=25.0`, `temporal_min_overlap_days=90`,
`seam_buffer_miles=20.0`.

## Next up for this branch

1. Wire `app/db.py::Repository` to real Postgres (asyncpg or SQLAlchemy +
   GeoAlchemy2) once ingestion starts producing real volume.
2. Flip `app/spatial.py::distance_miles` callers to `distance_miles_sql`.
3. Load real boundary geometry into the `boundaries` table for Seams Mode.
4. Add `GET /projects` pagination once volume warrants it.
5. Fix `scripts/seed_demo_data.py` to POST through the running API instead
   of writing directly to a standalone repository instance, so seeding
   actually populates the live server.