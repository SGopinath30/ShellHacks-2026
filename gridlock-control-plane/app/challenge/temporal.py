"""Milestone gaps and half-open construction windows are different signals."""
from .contracts import Construction, Milestone


def relationship(a, b):
    if isinstance(a, Milestone) and isinstance(b, Milestone):
        return {"type": "IN_SERVICE_GAP", "status": "KNOWN", "gap_days": abs((a.in_service_date - b.in_service_date).days)}
    if isinstance(a, Construction) and isinstance(b, Construction):
        minimum = max(0, (min(a.end_exclusive.earliest, b.end_exclusive.earliest) - max(a.start.latest, b.start.latest)).days)
        maximum = max(0, (min(a.end_exclusive.latest, b.end_exclusive.latest) - max(a.start.earliest, b.start.earliest)).days)
        return {"type": "CONSTRUCTION_WINDOW", "status": "CONFIRMED" if minimum > 0 else "POSSIBLE" if maximum > 0 else "NONE",
                "minimum_overlap_days": minimum, "maximum_overlap_days": maximum, "interval_convention": "HALF_OPEN",
                "partially_feasible": any(w.start.latest >= w.end_exclusive.earliest for w in (a, b))}
    return {"type": "UNKNOWN", "status": "UNAVAILABLE"}


def strength(value, config):
    if value["type"] == "CONSTRUCTION_WINDOW":
        return {"CONFIRMED": 0, "POSSIBLE": 1, "NONE": 3}[value["status"]]
    if value["type"] == "IN_SERVICE_GAP":
        return 2 if value["gap_days"] <= config.close_milestone_days else 3
    return 4
