"""Content-addressed raw bytes with a local SQLite source/job registry."""
import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path

from ingestion.common import IngestionError, digest, encoded, now, stable_id

ACCESS_CLASSES = ("PUBLIC_CONFIRMED", "PUBLIC_ASSUMED", "ACCESS_UNCLEAR", "CEII")


def check_access(access_class, handoff=False):
    if access_class not in ACCESS_CLASSES:
        raise IngestionError("INVALID_ACCESS_CLASS", str(access_class))
    if access_class == "CEII":
        raise IngestionError("CEII_REJECTED", "CEII must not enter SYNCHRO")
    if handoff and access_class == "ACCESS_UNCLEAR":
        raise IngestionError("ACCESS_REVIEW_REQUIRED", "Source is quarantined pending access review")


class Store:
    def __init__(self, root="data"):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS versions (
                    id TEXT PRIMARY KEY, source_id TEXT NOT NULL,
                    hash TEXT NOT NULL, metadata TEXT NOT NULL,
                    UNIQUE(source_id, hash)
                );
                CREATE TABLE IF NOT EXISTS jobs (id TEXT PRIMARY KEY, metadata TEXT NOT NULL);
            """)

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.root / "catalog.sqlite3", timeout=30)
        try:
            with db:
                yield db
        finally:
            db.close()

    def preserve(self, data, metadata):
        check_access(metadata["access_class"])
        for key in ("source_id", "title", "publisher", "source_type", "source_tier"):
            if not metadata.get(key):
                raise IngestionError("MISSING_METADATA", key)
        sha = digest(data)
        version_id = stable_id("SV", [metadata["source_id"], sha])
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT metadata FROM versions WHERE id=?", (version_id,)).fetchone()
            if row:
                existing = json.loads(row[0])
                # Re-uploading cannot promote quarantined bytes to public implicitly.
                self.raw_bytes(existing)
                return existing, True
            raw = Path("raw") / sha[:2] / sha
            target = self.root / raw
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.exists():
                if digest(target.read_bytes()) != sha:
                    raise IngestionError("RAW_INTEGRITY_ERROR", str(raw))
            else:
                with target.open("xb") as handle:
                    handle.write(data)
            record = {**metadata, "source_version_id": version_id, "sha256": sha,
                      "retrieved_at": metadata.get("retrieved_at") or now(),
                      "raw_path": raw.as_posix(), "size_bytes": len(data),
                      "public_access": metadata["access_class"] == "PUBLIC_CONFIRMED"}
            db.execute("INSERT INTO versions VALUES (?, ?, ?, ?)",
                       (version_id, metadata["source_id"], sha, encoded(record)))
        return record, False

    def raw_bytes(self, record):
        data = (self.root / record["raw_path"]).read_bytes()
        if digest(data) != record["sha256"]:
            raise IngestionError("RAW_INTEGRITY_ERROR", record["source_version_id"])
        return data

    def versions(self):
        with self.connect() as db:
            return [json.loads(row[0]) for row in db.execute("SELECT metadata FROM versions ORDER BY rowid")]

    def save_job(self, job):
        with self.connect() as db:
            db.execute("INSERT OR REPLACE INTO jobs VALUES (?, ?)", (job["job_id"], encoded(job)))

    def jobs(self):
        with self.connect() as db:
            return [json.loads(row[0]) for row in db.execute("SELECT metadata FROM jobs ORDER BY rowid")]
