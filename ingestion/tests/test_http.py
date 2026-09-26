from unittest.mock import Mock

import pytest
import requests

from ingestion.common import IngestionError
from ingestion.downloaders.http import fetch
from ingestion.jobs.pipeline import ingest
from ingestion.versioning.sources import Store


def response(status, content=b"public bytes"):
    result = Mock(status_code=status, url="https://example.org/resolved", headers={"Content-Type": "text/csv; charset=utf-8"})
    result.__enter__ = Mock(return_value=result)
    result.__exit__ = Mock(return_value=False)
    result.iter_content.return_value = iter([content])
    return result


def test_transient_failure_retries_then_preserves_final_url(monkeypatch):
    request = Mock(side_effect=[response(503), response(200)])
    sleep = Mock()
    monkeypatch.setattr("ingestion.downloaders.http.requests.request", request)
    monkeypatch.setattr("ingestion.downloaders.http.time.sleep", sleep)
    data, metadata = fetch("https://example.org/source")
    assert data == b"public bytes"
    assert metadata["resolved_url"] == "https://example.org/resolved"
    assert metadata["mime_type"] == "text/csv"
    assert request.call_count == 2
    sleep.assert_called_once_with(1)


def test_permanent_failure_is_not_retried(monkeypatch):
    request = Mock(return_value=response(403))
    monkeypatch.setattr("ingestion.downloaders.http.requests.request", request)
    with pytest.raises(IngestionError) as error:
        fetch("https://example.org/restricted")
    assert error.value.code == "HTTP_403"
    assert error.value.retryable is False
    assert request.call_count == 1


def test_timeout_is_bounded_and_persisted(monkeypatch, tmp_path):
    request = Mock(side_effect=requests.Timeout("Timed out"))
    monkeypatch.setattr("ingestion.downloaders.http.requests.request", request)
    monkeypatch.setattr("ingestion.downloaders.http.time.sleep", Mock())
    store = Store(tmp_path)
    with pytest.raises(IngestionError):
        ingest(store, url="https://example.org/source", file_format="csv", metadata={
            "source_id": "SOURCE", "title": "Test", "publisher": "Test", "source_type": "CSV",
            "source_tier": "A", "access_class": "PUBLIC_CONFIRMED"})
    assert request.call_count == 3
    job = store.jobs()[0]
    assert job["status"] == "FAILED"
    assert job["error"]["retryable"] is True
    assert job["error"]["error_code"] == "HTTP_TIMEOUT"
    assert store.versions() == []
