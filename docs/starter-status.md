# Actual starter import — 2026-09-26

Completed on `badri` using the organizer folder supplied by the user. This replaces the earlier synthetic-only milestone.

The original `Projects_Overlaps.xlsx` remains unchanged. SHA-256:

```text
fe01df4ed0691d55fd565784a7510ddfe4682316ff63fb70b963b934c5974f24
```

Workbook SourceVersion: `SV-68b11dcd2e02f1aa798ca6b4`.

The exact mapping is `ingestion/catalog/sperry_starter_mapping.json`: `projects` rows 2–11 and `overlaps` rows 2–7. All original row values, formula strings, raw dates, overlap distances, and time gaps were checked against the source. No workbook values were recalculated or refreshed.

| Result | Count |
| --- | ---: |
| Real starter projects | 10 |
| Original overlap fixture rows | 6 |
| Approximate two-endpoint segments | 6 |
| Approximate single points | 4 |
| OSM candidate associations | 16 |
| Preserved source versions in package | 7 |
| Passing automated tests | 26 |

OSM name filtering produced one candidate for `DESC_5`, seven for `GPC_2`, and eight for `GPC_3`. These are feature/project associations, not sixteen validated projects. The snapshots cover the Savannah region; Augusta and other regions still need discovery. No OSM candidate was found for `DESC_3` in these particular snapshots. This does not establish that its infrastructure is absent from OSM.

Four projects have a missing endpoint location:

| Starter ID | Missing endpoint |
| --- | --- |
| DESC_1 | Hooks Sub |
| DESC_2 | Hooks Sub |
| DESC_4 | Ft Johnson Sub |
| GPC_2 | PURRYSBURG |

The workbook also gives MCINTOSH latitude `32.352116` in both GPC_2 and GPC_3, but longitude `-81.175112` in GPC_2 and `-81.182105` in GPC_3. Both values are preserved. Mac should review this discrepancy rather than treating the same endpoint name as proof of one coordinate.

The seven sources are the workbook, two DOCX challenge guides, the supplied DESC 2024–2028 planning PDF, the Georgia Power 2025 IRP Volume 3 public-disclosure PDF, and two previously acquired Savannah OSM snapshots. Source metadata is checked in at `sources/catalog.json`. Supplied utility PDFs are listed as candidate evidence for the appropriate utility; their project association and currentness remain unverified. All ten projects still need a current-source check. Organizer-supplied documents carry `PUBLIC_ASSUMED`, so the handoff has `review_required: true`.

Local outputs (gitignored):

```text
data/live/fixtures/PKG-b8fa62d495ff092c9e54e9f4/
    starter_projects.json
    starter_overlaps.json
    geometry_candidates.json
    source_inventory.json
    quality_report.json
    mac_handoff.json
    mapping.json
    raw/
    evidence/
data/live/sperry_mac_handoff.zip
data/live/challenge_run.json
data/live/verification.json
```

The portable folder includes all seven original sources and their parsed evidence. All seven hashes were verified, and all 26 geometry candidates (10 starter + 16 OSM) passed reference and canonical geometry checks. Repeating the import reused existing source versions and cached parser output. No data was sent to a remote AI service, and no overlap calculation or project-association verification was performed.

Reproduce with the `challenge` command in the README. Share the complete ZIP/folder with Mac so the raw evidence travels with the JSON. The data files are local artifacts; they are not included merely by sharing this Git branch.
