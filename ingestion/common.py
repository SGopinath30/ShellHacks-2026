import hashlib
import json
from datetime import date, datetime, timezone
from pathlib import Path


class IngestionError(ValueError):
    def __init__(self, code, message, retryable=False):
        super().__init__(message)
        self.code = code
        self.retryable = retryable


def now():
    return datetime.now(timezone.utc).isoformat()


def json_value(value):
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    raise TypeError(f"Cannot serialize {type(value).__name__}")


def encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2,
                      default=json_value, allow_nan=False) + "\n"


def digest(data):
    return hashlib.sha256(data).hexdigest()


def stable_id(prefix, value):
    return f"{prefix}-{digest(encoded(value).encode())[:24]}"


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(encoded(value), encoding="utf-8")


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))
