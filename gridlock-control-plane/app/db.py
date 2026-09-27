"""
Data access layer.

For Phase 1 (build the deterministic engine before any DB is wired up) this
is a plain in-memory store, so `matching.py` and the API routes are usable
immediately. Swap `Repository` for a Postgres/PostGIS-backed implementation
once the docker-compose Postgres is up -- the interface (methods below)
should not need to change, so routers don't need to change either.
"""

from __future__ import annotations

from typing import Optional

from app.models import MatchResult, ProjectRecord, ReviewStatus


class Repository:
    def __init__(self) -> None:
        self._projects: dict[str, ProjectRecord] = {}
        self._matches: dict[str, MatchResult] = {}

    # -- Projects ------------------------------------------------------

    def upsert_project(self, project: ProjectRecord) -> ProjectRecord:
        self._projects[project.project_id] = project
        return project

    def get_project(self, project_id: str) -> Optional[ProjectRecord]:
        return self._projects.get(project_id)

    def list_projects(
        self,
        utility_id: Optional[str] = None,
        status: Optional[str] = None,
        project_type: Optional[str] = None,
    ) -> list[ProjectRecord]:
        results = list(self._projects.values())
        if utility_id:
            results = [p for p in results if p.utility_id == utility_id]
        if status:
            results = [p for p in results if p.status == status]
        if project_type:
            results = [p for p in results if p.project_type == project_type]
        return results

    # -- Matches ---------------------------------------------------------

    def replace_matches(self, matches: list[MatchResult]) -> None:
        self._matches = {m.match_id: m for m in matches}

    def get_match(self, match_id: str) -> Optional[MatchResult]:
        return self._matches.get(match_id)

    def list_matches(self) -> list[MatchResult]:
        return list(self._matches.values())

    def set_review_status(self, match_id: str, status: ReviewStatus) -> Optional[MatchResult]:
        match = self._matches.get(match_id)
        if match is None:
            return None
        match.review_status = status
        return match


# Single process-wide instance for the MVP. Replace with a DB-backed
# dependency-injected repository (e.g. via FastAPI `Depends`) once Postgres
# is live -- see PRD section 21, "PostgreSQL + PostGIS" layer.
repo = Repository()
