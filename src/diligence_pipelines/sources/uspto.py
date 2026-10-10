from __future__ import annotations

import json
import ssl
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import certifi

from diligence_pipelines.sources.base import RawCapture, SourceRequest


PATENTSVIEW_PATENTS_URL = "https://search.patentsview.org/api/v1/patent/"


def fetch_patents(query: str, api_key: str, max_results: int = 25, api_url: str = PATENTSVIEW_PATENTS_URL) -> RawCapture:
    if not api_key:
        raise ValueError("USPTO_API_KEY is required for live patent collection")
    if not query.strip():
        raise ValueError("Patent query must not be empty")
    if not 1 <= max_results <= 1000:
        raise ValueError("max_results must be between 1 and 1000")
    body = {
        "q": {"_text_all": {"patent_title": query}},
        "f": [
            "patent_id", "patent_title", "patent_date", "patent_type",
            "inventors.inventor_id", "inventors.inventor_name_first", "inventors.inventor_name_last",
            "assignees.assignee_id", "assignees.assignee_organization",
        ],
        "o": {"size": max_results},
    }
    uri = api_url.rstrip("/") + "/"
    request = Request(uri, data=json.dumps(body).encode(), method="POST", headers={
        "X-Api-Key": api_key, "Accept": "application/json", "Content-Type": "application/json",
        "User-Agent": "investment-diligence-pipelines/0.1",
    })
    context = ssl.create_default_context(cafile=certifi.where())
    try:
        with urlopen(request, timeout=30, context=context) as response:
            payload = response.read()
            status = getattr(response, "status", None)
    except HTTPError as exc:
        raise RuntimeError(
            f"USPTO patent endpoint returned HTTP {exc.code}: {uri}. "
            "Verify USPTO_API_URL and that the API key is valid for that endpoint."
        ) from exc
    except URLError as exc:
        raise RuntimeError(
            f"Unable to reach USPTO patent endpoint {uri}: {exc.reason}. "
            "The legacy PatentsView search API was paused during the 2026 USPTO Open Data Portal migration. "
            "Use --patent-fixture for offline tests or set USPTO_API_URL to a supported replacement endpoint."
        ) from exc
    return RawCapture(request=SourceRequest("uspto_patents", uri, {"query": query, "max_results": str(max_results)}), payload=payload, status_code=status or 200, adapter_version="patentsview-patent-1.0.0")


def normalize_patents(payload: bytes, run_id: str, source_record_id: str) -> tuple[list[dict], list[dict], list[dict]]:
    data = json.loads(payload)
    patents, assignments, inventor_edges = [], [], []
    for item in data.get("patents", []):
        patent_id = str(item.get("patent_id", ""))
        if not patent_id or not item.get("patent_title"):
            continue
        patent_record_id = f"patent:{patent_id}"
        patents.append({
            "record_id": patent_record_id, "schema_version": "1.0.0", "pipeline_id": "02_technology_talent",
            "source_id": "uspto_patents", "run_id": run_id, "patent_id": patent_id,
            "title": item["patent_title"], "patent_date": item.get("patent_date"),
            "patent_type": item.get("patent_type"), "source_record_id": source_record_id,
        })
        for assignee in item.get("assignees", []):
            assignments.append({
                "record_id": f"assignment:{patent_id}:{assignee.get('assignee_id', assignee.get('assignee_organization', 'unknown'))}",
                "schema_version": "1.0.0", "pipeline_id": "02_technology_talent", "source_id": "uspto_patents", "run_id": run_id,
                "patent_id": patent_id, "assignee_id": assignee.get("assignee_id"),
                "assignee_name": assignee.get("assignee_organization"), "source_record_id": source_record_id,
                "review_status": "unreviewed",
            })
        for inventor in item.get("inventors", []):
            inventor_id = inventor.get("inventor_id") or f"name:{inventor.get('inventor_name_first', '')}:{inventor.get('inventor_name_last', '')}"
            inventor_edges.append({
                "record_id": f"inventor_edge:{patent_id}:{inventor_id}",
                "schema_version": "1.0.0", "pipeline_id": "02_technology_talent", "source_id": "uspto_patents", "run_id": run_id,
                "patent_id": patent_id, "inventor_id": inventor_id,
                "inventor_name": " ".join(part for part in [inventor.get("inventor_name_first"), inventor.get("inventor_name_last")] if part),
                "source_record_id": source_record_id,
            })
    return patents, assignments, inventor_edges
