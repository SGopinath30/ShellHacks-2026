# Deploy the SYNCHRO API to Railway

This deploys the API and a separate persistent PostGIS database. The local
`127.0.0.1:8000` server and its Docker data do not move to Railway.

1. Commit the intended backend files on `feat/control-plane` and push that
   branch to the team's GitHub repository. Railway reads committed code from
   GitHub, not the uncommitted files on the Zenbook.

2. In Railway, create a project. Add Railway's
   [TimescaleDB + PostGIS template](https://railway.com/deploy/timescaledb-postgis)
   using **+ New → Template**. This template includes PostGIS 3.4.1 and a
   persistent database volume. Wait until the database service is running.
   The ordinary PostgreSQL template does not include PostGIS.

3. Add a second service **from the GitHub repository**. Select the branch
   containing this backend, then set **Root Directory** to
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
