# Deploy the SYNCHRO API to Railway

This deploys the API and a separate persistent PostGIS database. The local
`127.0.0.1:8000` server and its Docker data do not move to Railway.

1. Commit the intended backend files on `Kevin` and push that
   branch to the team's GitHub repository. Railway reads committed code from
   GitHub, not the uncommitted files on the Zenbook.

2. In Railway, create a project. Add Railway's
   [TimescaleDB + PostGIS template](https://railway.com/deploy/timescaledb-postgis)
   using **+ New → Template**. This template includes PostGIS 3.4.1 and a
   persistent database volume. Wait until the database service is running.
   The ordinary PostgreSQL template does not include PostGIS.

3. Add a second service **from the GitHub repository**. Select the branch
   `Kevin`, then set **Root Directory** to
   `/gridlock-control-plane`. Set its **Start Command** to:

   ```text
   python -m uvicorn app.main:app --host 0.0.0.0 --port $PORT
   ```

4. In the API service's **Variables** tab, create:

   - `DATABASE_URL`: a reference to the PostGIS service's private
     `DATABASE_URL`, such as `${{TimescaleDB.DATABASE_URL}}`. Use Railway's
     reference picker because the service name may differ.
   - `WRITE_API_KEY`: a long random secret, for example one generated locally
     with `openssl rand -hex 32`. Share it only with trusted importers. Do not
     commit it or put it in frontend JavaScript.

5. In the API service's **Pre-Deploy Command**, enter:

   ```text
   python -m scripts.init_challenge_db
   ```

   This creates the PostGIS extension and SYNCHRO tables before the web
   process starts. The command is idempotent. Set **Healthcheck Path** to
   `/health` and deploy the staged settings.

6. In the API service's **Settings → Networking → Public Networking**, click
   **Generate Domain**. Open `https://YOUR-DOMAIN/health`; it should show
   `"status":"ok"`, a PostGIS version, and `"schema":"ok"`. Then open
   `https://YOUR-DOMAIN/docs`.

7. Give Dell the API domain and the `WRITE_API_KEY` through a private team
   channel. Dell can import one normalized project JSON object per request:

   ```bash
   curl -X POST 'https://YOUR-DOMAIN/api/v1/project-versions' \
     -H 'Content-Type: application/json' \
     -H 'X-API-Key: YOUR-SECRET' \
     --data-binary @project.json
   ```

   Confirm with `GET /api/v1/projects` and
   `GET /api/v1/opportunities`. The Railway database starts empty; the ten
   local workbook fixtures are not automatically copied over. For a demo,
   open `/docs`, click **Authorize**, enter the API key, and submit a test
   project; or import verified utility records with curl.

When `WRITE_API_KEY` is configured, all POST/PUT/PATCH/DELETE requests need
the `X-API-Key` header. Local development remains open if this variable is
unset. The public GET endpoints are readable without a key.

## What the database migration does

The PostGIS template provides a running PostgreSQL server with PostGIS installed,
but the extension may not yet be enabled in the application database. The
pre-deploy command `python -m scripts.init_challenge_db` reads `DATABASE_URL`
and runs `db/challenge.sql` against that same database. The SQL enables the
PostGIS extension, creates the `synchro` schema, creates utility, project,
project-version, pair, review, and ingestion-job tables, and creates spatial
GiST indexes. The statements use `IF NOT EXISTS` so rerunning the command on
later deploys does not erase project data. It does not copy the Zenbook Docker
volume or load the organizer fixtures.

In the Railway API service, configure `DATABASE_URL` under **Variables** as a
reference to the PostGIS service variable, using the service name Railway
shows. Do not enter the local `127.0.0.1:55432` URL. Set the pre-deploy command
under the API service **Settings**, then deploy the staged changes. Open the
API service deployment logs. A successful migration prints a dictionary with
`status: ok`, a PostGIS version, and `schema: ok`. The API `/health` endpoint
should then return HTTP 200 with the same database status.

If migration fails with `connection refused`, verify the PostGIS service is
running and the API `DATABASE_URL` reference points to its private URL. If it
fails with `extension postgis is not available`, the selected database image
lacks PostGIS; use the PostGIS template. If it fails on permissions while
creating the extension, use the database service credentials supplied by the
template. The Railway database starts empty even when the local database has
projects; import records after deployment.
