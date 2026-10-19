from __future__ import annotations

import hashlib
import json
import re
import ssl
from datetime import datetime, timezone
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from urllib.request import Request

import certifi

from diligence_pipelines.sources.base import RawCapture, SourceRequest, open_url_with_retries


GDELT_DOC_API_URL = "https://api.gdeltproject.org/api/v2/doc/doc"
# The DOC API returns at most 250 articles per request.
MAX_RECORDS = 250
TRACKING_PARAMS = re.compile(r"^(utm_.*|fbclid|gclid|mc_cid|mc_eid|ocid|cmpid)$", re.IGNORECASE)


def build_gdelt_query(query: str, *, source_language: str | None = None, source_country: str | None = None) -> str:
    if not query.strip():
        raise ValueError("GDELT query must not be empty")
    parts = [query.strip()]
    if source_language:
        parts.append(f"sourcelang:{source_language}")
    if source_country:
        parts.append(f"sourcecountry:{source_country}")
    return " ".join(parts)


def fetch_gdelt_articles(
    query: str,
    *,
    max_records: int = 75,
    timespan: str | None = "7d",
    start_datetime: str | None = None,
    end_datetime: str | None = None,
    source_language: str | None = None,
    source_country: str | None = None,
    api_url: str = GDELT_DOC_API_URL,
) -> RawCapture:
    """Fetch one bounded GDELT DOC 2.0 article list.

    ``start_datetime``/``end_datetime`` use GDELT's ``YYYYMMDDHHMMSS`` format and
    take precedence over ``timespan`` when both are supplied.
    """
    params = {
        "query": build_gdelt_query(query, source_language=source_language, source_country=source_country),
        "mode": "artlist",
        "format": "json",
        "sort": "datedesc",
        "maxrecords": str(max(1, min(max_records, MAX_RECORDS))),
    }
    if start_datetime and end_datetime:
        params["startdatetime"] = start_datetime
        params["enddatetime"] = end_datetime
    elif timespan:
        params["timespan"] = timespan
    uri = f"{api_url}?{urlencode(params)}"
    request = Request(uri, headers={"Accept": "application/json", "User-Agent": "investment-diligence-pipelines/0.1"})
    context = ssl.create_default_context(cafile=certifi.where())
    with open_url_with_retries(request, timeout=45, context=context, backoff_seconds=5.0) as response:
        payload = response.read()
        status = getattr(response, "status", None)
    return RawCapture(SourceRequest("gdelt_doc", uri, params), payload, status_code=status or 200, adapter_version="gdelt-doc-1.0.0")


def load_gdelt_fixture(payload: bytes, *, source_uri: str) -> RawCapture:
    json.loads(payload)
    return RawCapture(SourceRequest("gdelt_doc_fixture", source_uri), payload, status_code=200, adapter_version="gdelt-doc-fixture-1.0.0")


def parse_gdelt_payload(payload: bytes) -> tuple[list[dict], str | None]:
    """Return (articles, error). GDELT answers some bad queries with plain text, not JSON."""
    text = payload.decode("utf-8", errors="replace").strip()
    if not text:
        return [], None
    try:
        data = json.loads(text, strict=False)
    except json.JSONDecodeError:
        return [], text[:500]
    articles = data.get("articles") if isinstance(data, dict) else None
    return (articles if isinstance(articles, list) else []), None


def gdelt_response_metadata(payload: bytes) -> dict:
    articles, error = parse_gdelt_payload(payload)
    return {
        "returned_row_count": len(articles),
        "languages": sorted({str(item.get("language")) for item in articles if item.get("language")}),
        "source_countries": sorted({str(item.get("sourcecountry")) for item in articles if item.get("sourcecountry")}),
        "error": error,
    }


def canonical_url(url: str) -> str:
    parts = urlsplit(url.strip())
    host = parts.netloc.casefold()
    host = host[4:] if host.startswith("www.") else host
    query = urlencode([(key, value) for key, value in parse_qsl(parts.query, keep_blank_values=True) if not TRACKING_PARAMS.match(key)])
    return urlunsplit((parts.scheme.casefold() or "https", host, parts.path.rstrip("/") or "/", query, ""))


def title_fingerprint(title: str) -> str:
    normalized = " ".join(re.sub(r"[^\w]+", " ", title.casefold()).split())
    return hashlib.sha256(normalized.encode()).hexdigest()[:16]


def parse_seendate(value: str | None) -> str | None:
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc).isoformat()
    except ValueError:
        return None


def normalize_gdelt_articles(payload: bytes, run_id: str, source_record_id: str) -> list[dict]:
    """Normalize article metadata and mark syndicated copies (same normalized title) as duplicates."""
    articles, _ = parse_gdelt_payload(payload)
    by_url: dict[str, dict] = {}
    for item in articles:
        url = item.get("url")
        title = (item.get("title") or "").strip()
        if not url or not title:
            continue
        key = canonical_url(url)
        document_id = hashlib.sha256(key.encode()).hexdigest()[:24]
        if key in by_url:
            continue
        by_url[key] = {
            "record_id": f"document:{document_id}",
            "schema_version": "1.0.0",
            "pipeline_id": "05_multilingual_events",
            "source_id": "gdelt_doc",
            "run_id": run_id,
            "document_id": document_id,
            "url": url,
            "canonical_url": key,
            "domain": item.get("domain") or urlsplit(key).netloc,
            "title": title,
            "language": item.get("language"),
            "source_country": item.get("sourcecountry"),
            # GDELT's seendate is when GDELT first observed the article, not the publisher's timestamp.
            "first_seen_at": parse_seendate(item.get("seendate")),
            "published_at": None,
            "syndication_key": title_fingerprint(title),
            "duplicate_of": None,
            "content_scope": "title_only",
            "source_record_id": source_record_id,
        }
    documents = sorted(by_url.values(), key=lambda row: (row["first_seen_at"] or "", row["document_id"]))
    first_by_title: dict[str, str] = {}
    for document in documents:
        original = first_by_title.setdefault(document["syndication_key"], document["document_id"])
        if original != document["document_id"]:
            document["duplicate_of"] = original
    return documents
