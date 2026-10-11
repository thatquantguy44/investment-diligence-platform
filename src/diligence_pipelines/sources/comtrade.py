from __future__ import annotations

import json
import ssl
from collections.abc import Sequence
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request

import certifi

from diligence_pipelines.sources.base import RawCapture, SourceRequest, open_url_with_retries


COMTRADE_API_URL = "https://comtradeapi.un.org/public/v1/preview/C/A/HS"


def _first_value(item: dict, *keys: str):
    for key in keys:
        value = item.get(key)
        if value is not None and value != "":
            return value
    return None


def fetch_comtrade(
    *,
    period: str,
    reporter_code: str,
    partner_code: str = "0",
    flow_code: str = "M,X",
    hs_codes: list[str] | None = None,
    api_key: str | None = None,
    api_keys: Sequence[str] | None = None,
    api_url: str = COMTRADE_API_URL,
) -> RawCapture:
    if not period.strip():
        raise ValueError("Comtrade period must not be empty")
    if not reporter_code.strip():
        raise ValueError("Comtrade reporter_code must not be empty")
    params = {
        "period": period,
        "reporterCode": reporter_code,
        "partnerCode": partner_code,
        "flowCode": flow_code,
        "cmdCode": ",".join(hs_codes or ["TOTAL"]),
        "partner2Code": "0",
        "motCode": "0",
        "customsCode": "C00",
        "breakdownMode": "classic",
        "includeDesc": "true",
        "typeCode": "C",
        "freqCode": "A" if len(period) == 4 else "M",
    }
    uri = f"{api_url}?{urlencode(params)}"
    context = ssl.create_default_context(cafile=certifi.where())
    configured_keys = tuple(dict.fromkeys(key for key in (api_keys or ((api_key,) if api_key else ())) if key))
    attempts = configured_keys or (None,)
    last_error: HTTPError | None = None
    for index, configured_key in enumerate(attempts):
        headers = {"Accept": "application/json", "User-Agent": "investment-diligence-pipelines/0.1"}
        if configured_key:
            headers["Ocp-Apim-Subscription-Key"] = configured_key
        request = Request(uri, headers=headers)
        try:
            with open_url_with_retries(request, timeout=45, context=context) as response:
                payload = response.read()
                status = getattr(response, "status", None)
            return RawCapture(SourceRequest("un_comtrade", uri, {key: str(value) for key, value in params.items()}), payload, status_code=status or 200, adapter_version="un-comtrade-1.0.0")
        except HTTPError as exc:
            last_error = exc
            if exc.code not in {401, 403, 429} or index == len(attempts) - 1:
                raise
            exc.close()
    if last_error:
        raise last_error
    raise RuntimeError("Comtrade request did not produce a response")


def load_comtrade_fixture(payload: bytes, *, source_uri: str) -> RawCapture:
    json.loads(payload)  # Fail early with a useful error for malformed fixtures.
    return RawCapture(SourceRequest("un_comtrade_fixture", source_uri), payload, status_code=200, adapter_version="un-comtrade-fixture-1.0.0")


def comtrade_response_metadata(payload: bytes) -> dict:
    """Extract response-level vintage, revision, and coverage metadata."""
    data = json.loads(payload)
    rows = data.get("data", data if isinstance(data, list) else [])
    rows = rows if isinstance(rows, list) else []
    source_vintages = sorted({str(value) for item in rows if isinstance(item, dict) for key in ("source_vintage", "dataVersion", "data_version", "release") if (value := item.get(key)) not in (None, "")})
    revision_fields = sorted({key for item in rows if isinstance(item, dict) for key in item if str(key).casefold() in {"isoriginal", "is_original", "revision", "revisiondate", "revision_date", "dataversion", "data_version", "source_vintage"}})
    response_count = data.get("count") if isinstance(data, dict) else None
    return {
        "response_count": response_count,
        "returned_row_count": len(rows),
        "source_vintages": source_vintages,
        "revision_fields_present": revision_fields,
        "error": data.get("error") if isinstance(data, dict) else None,
        "warning": data.get("warning") if isinstance(data, dict) else None,
    }


def normalize_trade_flows(payload: bytes, run_id: str, source_record_id: str, hs_codes: set[str] | None = None) -> list[dict]:
    data = json.loads(payload)
    rows = data.get("data", data if isinstance(data, list) else [])
    records = []
    for index, item in enumerate(rows):
        period_value = _first_value(item, "period", "periodDesc")
        hs_value = _first_value(item, "cmdCode", "hs_code")
        period = str(period_value) if period_value is not None else ""
        hs_code = str(hs_value) if hs_value is not None else ""
        if not period or not hs_code or (hs_codes and hs_code not in hs_codes):
            continue
        reporter_value = _first_value(item, "reporterCode", "reporter_code")
        partner_value = _first_value(item, "partnerCode", "partner_code")
        flow_value = _first_value(item, "flowDesc", "flow", "flowCode")
        reporter_code = str(reporter_value) if reporter_value is not None else ""
        partner_code = str(partner_value) if partner_value is not None else ""
        flow = str(flow_value).lower() if flow_value is not None else ""
        value = item.get("primaryValue", item.get("trade_value_usd"))
        if not reporter_code or not partner_code or not flow or value is None:
            continue
        identity = f"{period}|{reporter_code}|{partner_code}|{flow}|{hs_code}"
        source_vintage = next((item.get(key) for key in ("source_vintage", "dataVersion", "data_version", "release") if item.get(key) not in (None, "")), None)
        is_original = item.get("isOriginal", item.get("is_original"))
        records.append({
            "record_id": f"trade_flow:{identity}",
            "schema_version": "1.0.0",
            "pipeline_id": "03_trade_exposure",
            "source_id": "un_comtrade",
            "run_id": run_id,
            "trade_flow_id": identity,
            "period": period,
            "reporter_code": reporter_code,
            "reporter_name": item.get("reporterDesc", item.get("reporter_name")),
            "partner_code": partner_code,
            "partner_name": item.get("partnerDesc", item.get("partner_name")),
            "flow": flow,
            "hs_code": hs_code,
            "commodity_name": item.get("cmdDesc", item.get("commodity_name")),
            "trade_value_usd": float(value),
            "net_weight_kg": float(item["netWgt"]) if item.get("netWgt") is not None else item.get("net_weight_kg"),
            "quantity": float(item["qty"]) if item.get("qty") is not None else item.get("quantity"),
            "quantity_unit": item.get("qtyUnitAbbr", item.get("quantity_unit")),
            "source_vintage": source_vintage,
            "is_original": is_original,
            "source_record_id": source_record_id,
        })
    return records
