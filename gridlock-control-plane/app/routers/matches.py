from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.db import repo
from app.matching import compute_matches
from app.models import MatchRecomputeRequest, MatchResult, ReviewStateUpdate

router = APIRouter(prefix="/matches", tags=["matches"])


@router.get("", response_model=list[MatchResult])
def list_matches():
    return repo.list_matches()


@router.get("/{match_id}", response_model=MatchResult)
def get_match(match_id: str):
    match = repo.get_match(match_id)
    if match is None:
        raise HTTPException(status_code=404, detail="Match not found")
    return match


@router.post("/recompute", response_model=list[MatchResult])
def recompute_matches(req: MatchRecomputeRequest):
    """Recalculate every coordination opportunity from the current set of
    normalized projects and the given thresholds. Pure and reproducible:
    same projects + same thresholds -> same matches, every time."""
    projects = repo.list_projects()
    if req.utility_ids:
        projects = [p for p in projects if p.utility_id in req.utility_ids]

    matches = compute_matches(
        projects,
        spatial_threshold_miles=req.spatial_threshold_miles,
        temporal_min_overlap_days=req.temporal_min_overlap_days,
        seam_buffer_miles=req.seam_buffer_miles,
    )
    repo.replace_matches(matches)
    return matches


@router.post("/{match_id}/review", response_model=MatchResult)
def review_match(match_id: str, update: ReviewStateUpdate):
    match = repo.set_review_status(match_id, update.review_status)
    if match is None:
        raise HTTPException(status_code=404, detail="Match not found")
    return match
