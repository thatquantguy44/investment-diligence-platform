from urllib.error import URLError
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
