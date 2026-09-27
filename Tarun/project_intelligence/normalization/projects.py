"""Project-name and utility normalization."""

from __future__ import annotations

import re
import unicodedata


UTILITY_ALIASES = {
    "dominion energy south carolina": "DESC",
    "south carolina electric & gas": "DESC",
    "sce&g": "DESC",
    "desc": "DESC",
    "georgia power": "GPC",
    "georgia power company": "GPC",
    "southern company / georgia power": "GPC",
    "gpc": "GPC",
}


def normalize_project_name(value: object) -> str:
    text = unicodedata.normalize("NFKC", str(value)).strip()
    text = re.sub(r"[–—]", "-", text)
    return re.sub(r"\s+", " ", text)


def normalize_utility(value: object) -> str:
    text = normalize_project_name(value)
    return UTILITY_ALIASES.get(text.casefold(), text.upper())
