from __future__ import annotations

import hashlib
import time
import ssl
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Mapping
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


@dataclass(frozen=True)
class SourceRequest:
    source_id: str
    uri: str
    params: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class RawCapture:
    request: SourceRequest
    payload: bytes
    retrieved_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    status_code: int | None = None
    adapter_version: str = "1.0.0"

    @property
    def content_sha256(self) -> str:
        return hashlib.sha256(self.payload).hexdigest()


def open_url_with_retries(
    request: Request,
    *,
    timeout: float = 30,
    context: ssl.SSLContext | None = None,
    attempts: int = 3,
    backoff_seconds: float = 0.5,
):
    """Open a source request with bounded retries for transient failures.

    Only transport failures and HTTP 429/5xx responses are retried. The
    response is returned to the caller so it remains responsible for reading
    and closing the response body.
    """
    if attempts < 1:
        raise ValueError("attempts must be at least 1")
    for attempt in range(attempts):
        try:
            return urlopen(request, timeout=timeout, context=context)
        except HTTPError as exc:
            retryable = exc.code == 429 or 500 <= exc.code <= 599
            if not retryable or attempt == attempts - 1:
                raise
        except URLError:
            if attempt == attempts - 1:
                raise
        time.sleep(backoff_seconds * (2**attempt))
