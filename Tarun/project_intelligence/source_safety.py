"""Public-source and CEII enforcement."""

from __future__ import annotations

from project_intelligence.contracts import SourceAccess


class RestrictedSourceError(ValueError):
    pass


def ensure_remote_inference_allowed(source_access: SourceAccess) -> None:
    if source_access is not SourceAccess.PUBLIC:
        raise RestrictedSourceError(
            "remote inference requires an explicitly PUBLIC source; "
            f"received {source_access.value}"
        )
