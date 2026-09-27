import time
from urllib.parse import urlparse

import requests

from ingestion.common import IngestionError

MAX_BYTES = 100 * 1024 * 1024


def fetch(url, *, method="GET", data=None, attempts=3, user_agent="SYNCHRO-ingestion/0.1"):
    if urlparse(url).scheme not in ("https", "http"):
        raise IngestionError("INVALID_URL", "Only HTTP(S) public sources are supported")
    if not 1 <= attempts <= 5:
        raise ValueError("attempts must be between 1 and 5")
    for attempt in range(attempts):
        try:
            with requests.request(method, url, data=data, headers={"User-Agent": user_agent},
                                  timeout=(10, 45), stream=True) as response:
                retryable = response.status_code in (408, 429, 500, 502, 503, 504)
                if response.status_code >= 400:
                    raise IngestionError(f"HTTP_{response.status_code}",
                                         f"Public source request failed: {response.status_code}", retryable)
                chunks, size = [], 0
                for chunk in response.iter_content(65536):
                    size += len(chunk)
                    if size > MAX_BYTES:
                        raise IngestionError("SOURCE_TOO_LARGE", "Source exceeds the 100 MiB v0 limit")
                    chunks.append(chunk)
                return b"".join(chunks), {
                    "source_url": url, "resolved_url": response.url,
                    "mime_type": response.headers.get("Content-Type", "application/octet-stream").split(";")[0],
                    "etag": response.headers.get("ETag"),
                    "last_modified": response.headers.get("Last-Modified"),
                }
        except requests.RequestException as exc:
            error = IngestionError("HTTP_TIMEOUT" if isinstance(exc, requests.Timeout) else "HTTP_CONNECTION_ERROR",
                                   str(exc), retryable=True)
        except IngestionError as exc:
            error = exc
        if not error.retryable or attempt == attempts - 1:
            raise error
        time.sleep(2 ** attempt)
