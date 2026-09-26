import re

ALIASES = {
    "DESC": ["DESC", "Dominion Energy South Carolina", "Dominion Energy SC", "SCE&G",
             "South Carolina Electric & Gas"],
    "GPC": ["GPC", "Georgia Power", "Georgia Power Company", "Southern Company / Georgia Power"],
}


def normalize_name(value):
    return " ".join(re.findall(r"[a-z0-9]+", str(value).casefold()))


def utility_id(value):
    name = normalize_name(value)
    for utility, names in ALIASES.items():
        if name in {normalize_name(n) for n in names}:
            return utility
    return None
