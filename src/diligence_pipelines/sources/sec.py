from __future__ import annotations

import json
import gzip
import re
import ssl
from urllib.request import Request, urlopen

import certifi

from diligence_pipelines.sources.base import RawCapture, SourceRequest


SEC_SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik}.json"


def normalize_cik(cik: str) -> str:
    digits = re.sub(r"\D", "", cik)
    if not digits:
        raise ValueError("CIK must contain at least one digit")
    return digits.zfill(10)


def fetch_sec_submissions(cik: str, user_agent: str) -> RawCapture:
    normalized_cik = normalize_cik(cik)
    uri = SEC_SUBMISSIONS_URL.format(cik=normalized_cik)
    request = Request(uri, headers={"User-Agent": user_agent, "Accept-Encoding": "gzip, deflate"})
    tls_context = ssl.create_default_context(cafile=certifi.where())
    with urlopen(request, timeout=30, context=tls_context) as response:
        payload = response.read()
        status = getattr(response, "status", None)
        if response.headers.get("Content-Encoding", "").lower() == "gzip" or payload[:2] == b"\x1f\x8b":
            payload = gzip.decompress(payload)
    return RawCapture(
        request=SourceRequest("sec_edgar", uri),
        payload=payload,
        status_code=status or 200,
        adapter_version="sec-submissions-1.0.0",
    )


def normalize_sec_entity(payload: bytes, run_id: str) -> dict:
    data = json.loads(payload)
    cik = normalize_cik(str(data["cik"]))
    identifiers = [{"scheme": "sec_cik", "value": cik}]
    for ticker in data.get("tickers", []):
        identifiers.append({"scheme": "ticker", "value": str(ticker)})
    for exchange in data.get("exchanges", []):
        identifiers.append({"scheme": "exchange", "value": str(exchange)})
    return {
        "record_id": f"entity:sec:{cik}",
        "entity_id": f"entity:sec:{cik}",
        "schema_version": "1.0.0",
        "pipeline_id": "01_entity_graph",
        "source_id": "sec_edgar",
        "run_id": run_id,
        "entity_type": "organization",
        "canonical_name": data["name"],
        "jurisdiction": data.get("stateOfIncorporation") or data.get("stateOfIncorporationDescription"),
        "identifiers": identifiers,
        "entity_status": "active",
    }
