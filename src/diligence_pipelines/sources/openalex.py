from __future__ import annotations

import json
import ssl
from urllib.parse import urlencode
from urllib.request import Request

import certifi

from diligence_pipelines.sources.base import RawCapture, SourceRequest, open_url_with_retries


OPENALEX_WORKS_URL = "https://api.openalex.org/works"


def fetch_openalex_works(query: str, max_results: int = 25, email: str | None = None) -> RawCapture:
    if not query.strip():
        raise ValueError("OpenAlex query must not be empty")
    if not 1 <= max_results <= 200:
        raise ValueError("max_results must be between 1 and 200")
    params = {"search": query, "per-page": str(max_results)}
    if email:
        params["mailto"] = email
    uri = f"{OPENALEX_WORKS_URL}?{urlencode(params)}"
    request = Request(uri, headers={"User-Agent": "investment-diligence-pipelines/0.1"})
    context = ssl.create_default_context(cafile=certifi.where())
    with open_url_with_retries(
        request,
        timeout=30,
        context=context,
        attempts=5,
        backoff_seconds=2.0,
        max_backoff_seconds=60.0,
    ) as response:
        payload = response.read()
        status = getattr(response, "status", None)
    return RawCapture(request=SourceRequest("openalex", uri, params), payload=payload, status_code=status or 200, adapter_version="openalex-works-1.0.0")


def normalize_openalex_works(payload: bytes, run_id: str, source_record_id: str) -> list[dict]:
    data = json.loads(payload)
    records = []
    for item in data.get("results", []):
        authors = []
        institutions = []
        for authorship in item.get("authorships", []):
            author = authorship.get("author") or {}
            if author.get("id") or author.get("display_name"):
                authors.append({"id": author.get("id", ""), "name": author.get("display_name", "")})
            for institution in authorship.get("institutions", []):
                if institution.get("id") or institution.get("display_name"):
                    institutions.append({"id": institution.get("id", ""), "name": institution.get("display_name", "")})
        work_id = item.get("id") or item.get("doi")
        if not work_id or not item.get("title"):
            continue
        records.append({
            "record_id": f"research_work:{work_id}",
            "schema_version": "1.0.0", "pipeline_id": "02_technology_talent", "source_id": "openalex", "run_id": run_id,
            "work_id": work_id, "title": item["title"], "publication_date": item.get("publication_date"),
            "work_type": item.get("type"), "cited_by_count": item.get("cited_by_count"),
            "authors": authors, "institutions": institutions, "source_record_id": source_record_id,
        })
    return records
