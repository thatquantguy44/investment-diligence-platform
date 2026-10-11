from __future__ import annotations

import hashlib
import time
import ssl
from dataclasses import dataclass, field
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
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
    max_backoff_seconds: float = 60.0,
):
    """Open a source request with bounded retries for transient failures.

    Only transport failures and HTTP 429/5xx responses are retried. The
    response is returned to the caller so it remains responsible for reading
    and closing the response body.
    """
    if attempts < 1:
        raise ValueError("attempts must be at least 1")
    if backoff_seconds < 0 or max_backoff_seconds < 0:
        raise ValueError("backoff values must not be negative")
    if max_backoff_seconds < backoff_seconds:
        raise ValueError("max_backoff_seconds must be at least backoff_seconds")
    for attempt in range(attempts):
        try:
            return urlopen(request, timeout=timeout, context=context)
        except HTTPError as exc:
            retryable = exc.code == 429 or 500 <= exc.code <= 599
            if not retryable or attempt == attempts - 1:
                raise
            retry_after = _retry_after_seconds(exc, max_seconds=max_backoff_seconds)
        except URLError:
            if attempt == attempts - 1:
                raise
            retry_after = None
        delay = retry_after if retry_after is not None else min(backoff_seconds * (2**attempt), max_backoff_seconds)
        time.sleep(delay)


def _retry_after_seconds(error: HTTPError, *, now: datetime | None = None, max_seconds: float = 60.0) -> float | None:
    """Parse Retry-After seconds or HTTP-date, bounded for safe retries."""
    value = error.headers.get("Retry-After") if error.headers else None
    if not value:
        return None
    try:
        delay = float(value.strip())
    except ValueError:
        try:
            retry_at = parsedate_to_datetime(value)
            if retry_at.tzinfo is None:
                retry_at = retry_at.replace(tzinfo=timezone.utc)
            delay = (retry_at - (now or datetime.now(timezone.utc))).total_seconds()
        except (TypeError, ValueError, OverflowError):
            return None
    return min(max(0.0, delay), max_seconds)
