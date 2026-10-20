from __future__ import annotations

import json
import gzip
import re
import ssl
from datetime import date
from urllib.request import Request

import certifi

from diligence_pipelines.sources.base import RawCapture, SourceRequest, open_url_with_retries


SEC_SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik}.json"
SEC_COMPANYFACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
SEC_FILING_INDEX_URL = "https://www.sec.gov/Archives/edgar/data/{cik}/{accession}/"

ANNUAL_FORMS = ("10-K", "10-K/A", "20-F", "20-F/A", "40-F", "40-F/A")
# Bounded concept set: (taxonomy, concept) -> concept group. Revenue has several aliases because
# issuers tag it differently; the metric layer picks the first alias that has annual data.
CONCEPT_GROUPS: dict[tuple[str, str], str] = {
    ("us-gaap", "Revenues"): "revenue",
    ("us-gaap", "RevenueFromContractWithCustomerExcludingAssessedTax"): "revenue",
    ("us-gaap", "SalesRevenueNet"): "revenue",
    ("us-gaap", "ResearchAndDevelopmentExpense"): "rd_expense",
    ("us-gaap", "PaymentsToAcquirePropertyPlantAndEquipment"): "capex",
    ("us-gaap", "NetIncomeLoss"): "net_income",
    ("us-gaap", "OperatingIncomeLoss"): "operating_income",
    ("us-gaap", "Assets"): "total_assets",
}


def normalize_cik(cik: str) -> str:
    digits = re.sub(r"\D", "", cik)
    if not digits:
        raise ValueError("CIK must contain at least one digit")
    return digits.zfill(10)


def _fetch_sec_json(uri: str, user_agent: str, adapter_version: str, timeout: float = 30) -> RawCapture:
    request = Request(uri, headers={"User-Agent": user_agent, "Accept-Encoding": "gzip, deflate"})
    tls_context = ssl.create_default_context(cafile=certifi.where())
    with open_url_with_retries(request, timeout=timeout, context=tls_context) as response:
        payload = response.read()
        status = getattr(response, "status", None)
        if response.headers.get("Content-Encoding", "").lower() == "gzip" or payload[:2] == b"\x1f\x8b":
            payload = gzip.decompress(payload)
    return RawCapture(
        request=SourceRequest("sec_edgar", uri),
        payload=payload,
        status_code=status or 200,
        adapter_version=adapter_version,
    )


def fetch_sec_submissions(cik: str, user_agent: str) -> RawCapture:
    return _fetch_sec_json(SEC_SUBMISSIONS_URL.format(cik=normalize_cik(cik)), user_agent, "sec-submissions-1.0.0")


def fetch_sec_companyfacts(cik: str, user_agent: str) -> RawCapture:
    """Fetch one company's XBRL facts; large filers return several megabytes."""
    return _fetch_sec_json(SEC_COMPANYFACTS_URL.format(cik=normalize_cik(cik)), user_agent, "sec-companyfacts-1.0.0", timeout=90)


def load_sec_facts_fixture(payload: bytes, *, source_uri: str) -> RawCapture:
    json.loads(payload)
    return RawCapture(SourceRequest("sec_edgar_fixture", source_uri), payload, status_code=200, adapter_version="sec-companyfacts-fixture-1.0.0")


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


def sec_facts_metadata(payload: bytes) -> dict:
    """Response-level summary; SEC answers unknown CIKs with a non-JSON or error body."""
    try:
        data = json.loads(payload)
    except json.JSONDecodeError:
        return {"cik": None, "entity_name": None, "taxonomies": [], "concept_count": 0, "error": payload.decode("utf-8", errors="replace")[:300]}
    facts = data.get("facts") if isinstance(data, dict) else None
    if not isinstance(facts, dict):
        return {"cik": None, "entity_name": None, "taxonomies": [], "concept_count": 0, "error": "Response has no facts object"}
    return {
        "cik": normalize_cik(str(data["cik"])) if data.get("cik") is not None else None,
        "entity_name": data.get("entityName"),
        "taxonomies": sorted(facts),
        "concept_count": sum(len(concepts) for concepts in facts.values()),
        "error": None,
    }


def _duration_days(start: str | None, end: str | None) -> int | None:
    if not start or not end:
        return None
    try:
        return (date.fromisoformat(end) - date.fromisoformat(start)).days
    except ValueError:
        return None


def normalize_financial_facts(payload: bytes, run_id: str, source_record_id: str, forms: tuple[str, ...] = ANNUAL_FORMS) -> list[dict]:
    """Normalize a bounded concept set into point-in-time observations.

    Every filing that reports a value is kept as its own observation: ``period_end`` is
    when the figure applies and ``filed_at`` is when the SEC received it, so restated
    values stay distinguishable. Only USD facts from the requested form types are kept.
    """
    data = json.loads(payload)
    cik = normalize_cik(str(data["cik"]))
    entity_id = f"entity:sec:{cik}"
    records = []
    for (taxonomy, concept), group in CONCEPT_GROUPS.items():
        node = (data.get("facts") or {}).get(taxonomy, {}).get(concept)
        if not node:
            continue
        for item in (node.get("units") or {}).get("USD") or []:
            if item.get("form") not in forms or item.get("val") is None or not item.get("end") or not item.get("accn"):
                continue
            start = item.get("start")
            fact_id = f"fact:{cik}:{taxonomy}:{concept}:{start or 'instant'}:{item['end']}:{item['accn']}"
            records.append({
                "record_id": fact_id,
                "schema_version": "1.0.0",
                "pipeline_id": "01_entity_graph",
                "source_id": "sec_edgar",
                "run_id": run_id,
                "fact_id": fact_id,
                "entity_id": entity_id,
                "cik": cik,
                "taxonomy": taxonomy,
                "concept": concept,
                "concept_group": group,
                "label": node.get("label"),
                "unit": "USD",
                "value": float(item["val"]),
                "period_start": start,
                "period_end": item["end"],
                "duration_days": _duration_days(start, item["end"]),
                "form": item["form"],
                "accession_number": item["accn"],
                # fy/fp describe the filing, not the period the value covers; keep them only as reported.
                "fiscal_year_reported": item.get("fy"),
                "fiscal_period_reported": item.get("fp"),
                "frame": item.get("frame"),
                "filed_at": item.get("filed"),
                "filing_index_url": SEC_FILING_INDEX_URL.format(cik=int(cik), accession=item["accn"].replace("-", "")),
                "source_record_id": source_record_id,
            })
    return sorted(records, key=lambda row: (row["concept_group"], row["concept"], row["period_end"], row["filed_at"] or "", row["accession_number"]))
