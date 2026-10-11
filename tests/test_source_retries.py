from datetime import datetime, timezone
from email.message import Message
from email.utils import format_datetime
from urllib.error import HTTPError, URLError
from urllib.request import Request

import pytest

from diligence_pipelines.sources import base


def test_open_url_retries_transport_failure(monkeypatch):
    calls = []

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    def fake_urlopen(request, timeout, context):
        calls.append(request.full_url)
        if len(calls) < 3:
            raise URLError("temporary DNS failure")
        return Response()

    monkeypatch.setattr(base, "urlopen", fake_urlopen)
    monkeypatch.setattr(base.time, "sleep", lambda _: None)
    response = base.open_url_with_retries(Request("https://example.test"), attempts=3)
    assert isinstance(response, Response)
    assert len(calls) == 3


def test_open_url_does_not_retry_invalid_attempt_count():
    with pytest.raises(ValueError, match="attempts"):
        base.open_url_with_retries(Request("https://example.test"), attempts=0)


def test_open_url_honors_numeric_retry_after(monkeypatch):
    calls = []
    sleeps = []

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    def fake_urlopen(request, timeout, context):
        calls.append(request.full_url)
        if len(calls) == 1:
            headers = Message()
            headers["Retry-After"] = "7"
            raise HTTPError(request.full_url, 429, "rate limited", headers, None)
        return Response()

    monkeypatch.setattr(base, "urlopen", fake_urlopen)
    monkeypatch.setattr(base.time, "sleep", sleeps.append)
    base.open_url_with_retries(Request("https://example.test"), attempts=2, backoff_seconds=1)
    assert calls == ["https://example.test", "https://example.test"]
    assert sleeps == [7.0]


def test_retry_after_http_date_is_parsed():
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    headers = Message()
    headers["Retry-After"] = format_datetime(datetime(2026, 1, 1, 0, 0, 10, tzinfo=timezone.utc), usegmt=True)
    error = HTTPError("https://example.test", 429, "rate limited", headers, None)
    assert base._retry_after_seconds(error, now=now) == 10.0
