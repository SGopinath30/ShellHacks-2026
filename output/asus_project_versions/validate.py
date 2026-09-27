"""Validate all handoff records against the saved live API schema."""

import json
from pathlib import Path

from jsonschema import Draft202012Validator, RefResolver


BASE = Path(__file__).resolve().parent
spec = json.loads((BASE / "openapi.json").read_text(encoding="utf-8"))
schema = spec["components"]["schemas"]["ProjectInput"]
validator = Draft202012Validator(schema, resolver=RefResolver.from_schema(spec))

files = sorted((BASE / "source_backed_needs_review").glob("*.json")) + sorted((BASE / "starter_fixtures").glob("*.json"))
assert len(files) == 12, f"Expected 12 records, found {len(files)}"
ids = set()
for path in files:
    record = json.loads(path.read_text(encoding="utf-8"))
    errors = list(validator.iter_errors(record))
    assert not errors, f"{path}: {errors}"
    assert record["project_id"] not in ids
    ids.add(record["project_id"])
    assert record["is_fixture"] == (path.parent.name == "starter_fixtures")
    assert record["geometry"]["type"] in {"Point", "LineString"}
    if record["geometry"]["type"] == "LineString":
        assert record["geometry_origin"] == "TWO_ENDPOINT_SEGMENT"
        assert record["geometry_quality"] == "APPROXIMATE"
    assert record["validation_state"] == "NEEDS_REVIEW"

print(f"Validated {len(files)} unique, one-object project files against ProjectInput")
