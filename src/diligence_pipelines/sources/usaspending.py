from __future__ import annotations

import json
import ssl
from urllib.request import Request

import certifi

from diligence_pipelines.sources.base import RawCapture, SourceRequest, open_url_with_retries


USASPENDING_AWARD_SEARCH_URL = "https://api.usaspending.gov/api/v2/search/spending_by_award/"
USASPENDING_TRANSACTIONS_URL = "https://api.usaspending.gov/api/v2/transactions/"
USASPENDING_AWARD_PAGE_URL = "https://www.usaspending.gov/award/"

AWARD_TYPE_CODES = {
    "contracts": ["A", "B", "C", "D"],
    "grants": ["02", "03", "04", "05"],
}
COMMON_FIELDS = [
    "Award ID", "Recipient Name", "Recipient UEI", "recipient_id",
    "Award Amount", "Total Outlays", "Description",
    "Start Date", "End Date", "Base Obligation Date", "Last Modified Date",
    "Awarding Agency", "Awarding Sub Agency", "Funding Agency", "Funding Sub Agency",
    "generated_internal_id",
]
AWARD_FIELDS = {
    "contracts": COMMON_FIELDS + ["Contract Award Type", "NAICS", "PSC"],
    "grants": COMMON_FIELDS + ["Award Type", "Assistance Listings", "CFDA Number"],
}
# The award search endpoint caps page size at 100.
MAX_PAGE_SIZE = 100


def _context() -> ssl.SSLContext:
    return ssl.create_default_context(cafile=certifi.where())


def _post_json(source_id: str, uri: str, body: dict, adapter_version: str) -> RawCapture:
    data = json.dumps(body, sort_keys=True).encode()
    request = Request(uri, data=data, method="POST", headers={
        "Accept": "application/json",
        "Content-Type": "application/json",
        "User-Agent": "investment-diligence-pipelines/0.1",
    })
    with open_url_with_retries(request, timeout=60, context=_context()) as response:
        payload = response.read()
        status = getattr(response, "status", None)
    params = {"body": json.dumps(body, sort_keys=True)}
    return RawCapture(SourceRequest(source_id, uri, params), payload, status_code=status or 200, adapter_version=adapter_version)


def build_award_search_body(
    *,
    award_group: str,
    start_date: str,
    end_date: str,
    naics_codes: list[str] | None = None,
    psc_codes: list[str] | None = None,
    keywords: list[str] | None = None,
    awarding_agencies: list[str] | None = None,
    page: int = 1,
    limit: int = MAX_PAGE_SIZE,
) -> dict:
    if award_group not in AWARD_TYPE_CODES:
        raise ValueError(f"award_group must be one of: {', '.join(sorted(AWARD_TYPE_CODES))}")
    if not start_date or not end_date:
        raise ValueError("USAspending start_date and end_date are required")
    if not (naics_codes or psc_codes or keywords):
        raise ValueError("Provide at least one NAICS code, PSC code, or keyword to bound the award search")
    filters: dict = {
        "award_type_codes": AWARD_TYPE_CODES[award_group],
        "time_period": [{"start_date": start_date, "end_date": end_date}],
    }
    if naics_codes:
        filters["naics_codes"] = {"require": list(naics_codes)}
    if psc_codes:
        filters["psc_codes"] = {"require": [[code] for code in psc_codes]}
    if keywords:
        filters["keywords"] = list(keywords)
    if awarding_agencies:
        filters["agencies"] = [{"type": "awarding", "tier": "toptier", "name": name} for name in awarding_agencies]
    return {
        "filters": filters,
        "fields": AWARD_FIELDS[award_group],
        "page": page,
        "limit": max(1, min(limit, MAX_PAGE_SIZE)),
        "sort": "Award Amount",
        "order": "desc",
        "subawards": False,
    }


def fetch_award_search(
    *,
    award_group: str,
    start_date: str,
    end_date: str,
    naics_codes: list[str] | None = None,
    psc_codes: list[str] | None = None,
    keywords: list[str] | None = None,
    awarding_agencies: list[str] | None = None,
    max_records: int = 100,
    api_url: str = USASPENDING_AWARD_SEARCH_URL,
) -> list[RawCapture]:
    """Fetch a bounded set of award-search pages; one raw capture per page."""
    if max_records < 1:
        raise ValueError("max_records must be at least 1")
    captures = []
    page = 1
    remaining = max_records
    while remaining > 0:
        body = build_award_search_body(
            award_group=award_group, start_date=start_date, end_date=end_date,
            naics_codes=naics_codes, psc_codes=psc_codes, keywords=keywords,
            awarding_agencies=awarding_agencies, page=page, limit=min(remaining, MAX_PAGE_SIZE),
        )
        capture = _post_json("usaspending", api_url, body, "usaspending-awards-1.0.0")
        captures.append(capture)
        data = json.loads(capture.payload)
        returned = len(data.get("results") or [])
        remaining -= returned
        if not returned or not (data.get("page_metadata") or {}).get("hasNext"):
            break
        page += 1
    return captures


def fetch_award_transactions(award_id: str, *, limit: int = 100, api_url: str = USASPENDING_TRANSACTIONS_URL) -> RawCapture:
    """Fetch the transaction (modification) history for one award."""
    if not award_id:
        raise ValueError("award_id must not be empty")
    body = {"award_id": award_id, "limit": max(1, min(limit, 5000)), "page": 1, "sort": "action_date", "order": "asc"}
    return _post_json("usaspending_transactions", api_url, body, "usaspending-transactions-1.0.0")


def load_usaspending_fixture(payload: bytes, *, source_uri: str) -> dict[str, RawCapture | dict[str, RawCapture]]:
    """Split a fixture bundle into an award-search capture and per-award transaction captures.

    Fixture shape: ``{"awards": <spending_by_award response>, "transactions": {award_id: <transactions response>}}``.
    """
    bundle = json.loads(payload)
    awards = RawCapture(SourceRequest("usaspending_fixture", source_uri), json.dumps(bundle["awards"], sort_keys=True).encode(), status_code=200, adapter_version="usaspending-fixture-1.0.0")
    transactions = {
        award_id: RawCapture(SourceRequest("usaspending_fixture", f"{source_uri}#transactions/{award_id}"), json.dumps(body, sort_keys=True).encode(), status_code=200, adapter_version="usaspending-fixture-1.0.0")
        for award_id, body in (bundle.get("transactions") or {}).items()
    }
    return {"awards": awards, "transactions": transactions}


def award_search_metadata(payloads: list[bytes]) -> dict:
    """Summarize page counts, truncation, and API messages across award-search pages."""
    returned = 0
    has_next = False
    messages: list[str] = []
    error = None
    for payload in payloads:
        data = json.loads(payload)
        returned += len(data.get("results") or [])
        has_next = bool((data.get("page_metadata") or {}).get("hasNext"))
        messages.extend(str(message) for message in data.get("messages") or [])
        error = error or data.get("detail")
    return {
        "page_count": len(payloads),
        "returned_row_count": returned,
        "truncated": has_next,
        "messages": messages,
        "error": error,
    }


def _classification(value) -> tuple[str | None, str | None]:
    """Return (code, description) for a NAICS/PSC field that may be a string or object."""
    if isinstance(value, dict):
        code = value.get("code")
        return (str(code) if code not in (None, "") else None, value.get("description"))
    if value in (None, ""):
        return (None, None)
    return (str(value), None)


def _assistance_listings(item: dict) -> list[dict]:
    listings = item.get("Assistance Listings")
    if isinstance(listings, list):
        return [{"code": str(row.get("cfda_number")), "description": row.get("cfda_program_title")} for row in listings if isinstance(row, dict) and row.get("cfda_number")]
    cfda = item.get("CFDA Number")
    return [{"code": str(cfda), "description": None}] if cfda else []


def _amount(value) -> float | None:
    return float(value) if value not in (None, "") else None


def normalize_awards(payload: bytes, run_id: str, source_record_id: str, award_group: str) -> list[dict]:
    data = json.loads(payload)
    records = []
    for item in data.get("results") or []:
        award_id = item.get("generated_internal_id")
        if not award_id:
            continue
        naics_code, naics_description = _classification(item.get("NAICS"))
        psc_code, psc_description = _classification(item.get("PSC"))
        records.append({
            "record_id": f"award:{award_id}",
            "schema_version": "1.0.0",
            "pipeline_id": "04_public_awards",
            "source_id": "usaspending",
            "run_id": run_id,
            "award_id": award_id,
            "award_display_id": item.get("Award ID"),
            "award_group": award_group,
            "award_type": item.get("Contract Award Type") or item.get("Award Type"),
            "recipient_name": item.get("Recipient Name"),
            "recipient_uei": item.get("Recipient UEI") or None,
            "recipient_hash": item.get("recipient_id") or None,
            "awarding_agency": item.get("Awarding Agency"),
            "awarding_sub_agency": item.get("Awarding Sub Agency"),
            "funding_agency": item.get("Funding Agency"),
            "funding_sub_agency": item.get("Funding Sub Agency"),
            "description": item.get("Description"),
            "naics_code": naics_code,
            "naics_description": naics_description,
            "psc_code": psc_code,
            "psc_description": psc_description,
            "assistance_listings": _assistance_listings(item),
            # Amounts are kept separate: obligation is committed funding, outlay is disbursed funding.
            # USAspending does not publish an announcement amount, so it stays null rather than inferred.
            "obligated_amount_usd": _amount(item.get("Award Amount")),
            "outlay_amount_usd": _amount(item.get("Total Outlays")),
            "announced_amount_usd": None,
            "base_obligation_date": item.get("Base Obligation Date") or None,
            "period_of_performance_start": item.get("Start Date") or None,
            "period_of_performance_end": item.get("End Date") or None,
            "source_last_modified_date": item.get("Last Modified Date") or None,
            "source_url": f"{USASPENDING_AWARD_PAGE_URL}{award_id}",
            "source_record_id": source_record_id,
        })
    return records


def normalize_award_transactions(payload: bytes, award_id: str, run_id: str, source_record_id: str) -> list[dict]:
    data = json.loads(payload)
    records = []
    for item in data.get("results") or []:
        transaction_id = item.get("id")
        if not transaction_id:
            continue
        records.append({
            "record_id": f"award_event:{transaction_id}",
            "schema_version": "1.0.0",
            "pipeline_id": "04_public_awards",
            "source_id": "usaspending",
            "run_id": run_id,
            "award_event_id": transaction_id,
            "award_id": award_id,
            "action_date": item.get("action_date") or None,
            "action_type": item.get("action_type") or None,
            "action_type_description": item.get("action_type_description") or None,
            "modification_number": item.get("modification_number") or None,
            "federal_action_obligation_usd": _amount(item.get("federal_action_obligation")),
            "description": item.get("description"),
            "source_record_id": source_record_id,
        })
    return records
