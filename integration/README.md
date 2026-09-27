# SYNCHRO integration path

The three code paths share contracts but have separate data stores. Run this sequence from the repository root:

1. **Badri → Tarun:** Convert a portable Dell package. This verifies the preserved source hashes before creating canonical candidates.

   ```powershell
   $env:PYTHONPATH='Tarun;gridlock-control-plane'
   .venv/Scripts/python.exe -m project_intelligence.extraction.dell_handoff data/live/sperry_mac_handoff/PKG-b8fa62d495ff092c9e54e9f4 --output data/derived/canonical_candidate_projects.json
   ```

2. **Tarun review:** Obtain current public sources, run Phase B/C, resolve identity and site geometry, and create `AcceptedProjectVersion` files with Tarun's validation functions. Starter candidates and unresolved geometry must stay in review. The local Dell starter package currently produces ten `NEEDS_REVIEW` candidates and zero accepted candidates. `data/live/current_sources` is not present in this checkout.

3. **Tarun → Kevin:** Convert accepted files into one ASUS `ProjectInput` JSON file per project. This command validates each result against Kevin's actual Pydantic contract. It preserves the Mac version and candidate IDs. Unaccepted geometry is omitted and marked `UNRESOLVED`; starter records remain fixtures.

   ```powershell
   .venv/Scripts/python.exe -m integration.handoff --accepted path/to/accepted_versions --source-manifest path/to/source_manifest.json --output-dir data/derived/asus_import
   ```

4. **Kevin → frontend:** A trusted importer sends each reviewed JSON file to `POST /api/v1/project-versions` with the server's write key. The frontend uses public GET endpoints for project versions, location review, pair assessment, and qualified opportunities. An authorized reviewer may enter the key in the web UI for protected verification, ledger reads, and decisions; the key is held only in tab memory. Uploads are not performed by this adapter.

The deployed Railway API currently holds two unresolved source-backed records and produces zero opportunities. Its OpenAPI schema lacks `/api/v1/location-review-queue`, `/api/v1/pair-assessments`, and `/api/v1/qualified-pairs`, although those routes are in `main`. The Railway guide originally selected the `Kevin` branch. Deploy the current control-plane code and run the idempotent database pre-deploy command to expose the complete frontend contract. A verified DESC–Georgia Power pair still requires project-specific coordinates and current status evidence; the software must not manufacture that pair.
