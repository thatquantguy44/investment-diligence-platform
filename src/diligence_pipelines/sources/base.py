from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Mapping


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
