"""Project identity and immutable-version reconciliation."""

from project_intelligence.reconciliation.project_identity import reconcile_projects
from project_intelligence.reconciliation.versioning import (
    accept_candidate_version,
    compare_versions,
)

__all__ = ["accept_candidate_version", "compare_versions", "reconcile_projects"]
