from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class BaseRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")
    record_id: str
    schema_version: str = "1.0.0"
    pipeline_id: str
    source_id: str
    run_id: str
    created_at: datetime = Field(default_factory=utc_now)


class SourceRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source_record_id: str
    source_id: str
    source_uri: str
    retrieved_at: datetime
    published_at: datetime | None = None
    source_updated_at: datetime | None = None
    content_sha256: str
    http_status: int | None = None
    request_fingerprint: str | None = None
    adapter_version: str
    raw_object_uri: str


class EvidenceRef(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source_record_id: str
    locator: str
    quote_or_excerpt: str | None = None
    content_sha256: str


class Entity(BaseRecord):
    entity_id: str
    entity_type: str
    canonical_name: str
    jurisdiction: str | None = None
    identifiers: list[dict[str, str]] = Field(default_factory=list)
    first_seen_at: datetime | None = None
    entity_status: Literal["active", "inactive", "unknown"] = "unknown"
    evidence_refs: list[EvidenceRef] = Field(default_factory=list)


class EntityAlias(BaseRecord):
    entity_id: str
    alias: str
    language: str | None = None
    script: str | None = None
    transliteration_method: str | None = None
    match_method: str
    match_score: float = Field(ge=0, le=1)
    review_status: Literal["unreviewed", "accepted", "rejected"] = "unreviewed"


class MatchCandidateRecord(BaseRecord):
    candidate_id: str
    query: str
    candidate_entity_id: str
    match_method: str
    match_score: float = Field(ge=0, le=1)
    candidate_evidence: list[EvidenceRef] = Field(default_factory=list)
    review_status: Literal["unreviewed", "accepted", "rejected"] = "unreviewed"


class ResearchWork(BaseRecord):
    work_id: str
    title: str
    publication_date: str | None = None
    work_type: str | None = None
    cited_by_count: int | None = Field(default=None, ge=0)
    authors: list[dict[str, str]] = Field(default_factory=list)
    institutions: list[dict[str, str]] = Field(default_factory=list)
    source_record_id: str


class TopicObservation(BaseRecord):
    observation_id: str
    entity_id: str | None = None
    metric: str
    value: float
    unit: str
    period_start: str | None = None
    period_end: str | None = None
    input_record_ids: list[str] = Field(default_factory=list)
    formula_version: str
    limitations: list[str] = Field(default_factory=list)


class QualityResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    check_id: str
    status: Literal["pass", "warn", "fail"]
    measured_at: datetime = Field(default_factory=utc_now)
    partition_key: str | None = None
    observed_value: Any = None
    threshold: Any = None
    details: str | None = None
