from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.db import repo
from app.models import ProjectRecord
from app.matching import compute_matches

router = APIRouter(prefix="/projects", tags=["projects"])


@router.get("", response_model=list[ProjectRecord])
def list_projects(
    utility: str | None = None,
    status: str | None = None,
    project_type: str | None = None,
):
    return repo.list_projects(utility_id=utility, status=status, project_type=project_type)


@router.get("/{project_id}", response_model=ProjectRecord)
def get_project(project_id: str):
    project = repo.get_project(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


@router.post("", response_model=ProjectRecord)
def upsert_project(project: ProjectRecord):
    """Register/update a normalized project record. Auto-recomputes matches
    using this app's default thresholds after every save, so /matches stays
    fresh without a manual /matches/recompute call."""
    saved = repo.upsert_project(project)

    all_projects = repo.list_projects()
    matches = compute_matches(
        all_projects,
        spatial_threshold_miles=1.0,
        temporal_min_overlap_days=30,
    )
    repo.replace_matches(matches)

    return saved