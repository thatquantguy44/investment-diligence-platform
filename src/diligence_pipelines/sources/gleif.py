from __future__ import annotations

import json
import ssl
from urllib.request import Request

import certifi

from diligence_pipelines.sources.base import RawCapture, SourceRequest, open_url_with_retries


GLEIF_LEI_URL = "https://api.gleif.org/api/v1/lei-records/{lei}"


def normalize_lei(lei: str) -> str:
    normalized = lei.strip().upper()
    if len(normalized) != 20 or not normalized.isalnum():
        raise ValueError("LEI must be a 20-character alphanumeric identifier")
    return normalized


def fetch_gleif_lei(lei: str) -> RawCapture:
    normalized_lei = normalize_lei(lei)
    uri = GLEIF_LEI_URL.format(lei=normalized_lei)
    request = Request(uri, headers={"User-Agent": "investment-diligence-pipelines/0.1"})
    context = ssl.create_default_context(cafile=certifi.where())
    with open_url_with_retries(request, timeout=30, context=context) as response:
        payload = response.read()
        status = getattr(response, "status", None)
    return RawCapture(
        request=SourceRequest("gleif", uri),
        payload=payload,
        status_code=status or 200,
        adapter_version="gleif-lei-record-1.0.0",
    )


def normalize_gleif_alias(payload: bytes, run_id: str, entity_id: str) -> dict:
    data = json.loads(payload)["data"]
    attributes = data["attributes"]
    entity = attributes["entity"]
    legal_name = entity["legalName"]["name"]
    return {
        "record_id": f"alias:gleif:{data['id']}",
        "schema_version": "1.0.0",
        "pipeline_id": "01_entity_graph",
        "source_id": "gleif",
        "run_id": run_id,
        "entity_id": entity_id,
        "alias": legal_name,
        "language": None,
        "script": None,
        "transliteration_method": None,
        "match_method": "lei_exact",
        "match_score": 1.0,
        "review_status": "accepted",
        "lei": data["id"],
    }
