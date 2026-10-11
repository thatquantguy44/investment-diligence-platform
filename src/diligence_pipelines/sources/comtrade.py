from __future__ import annotations

import json
import ssl
from urllib.parse import urlencode
from urllib.request import Request

import certifi

from diligence_pipelines.sources.base import RawCapture, SourceRequest, open_url_with_retries


COMTRADE_API_URL = "https://comtradeapi.un.org/public/v1/preview/C/A/HS"


def fetch_comtrade(
    *,
    period: str,
    reporter_code: str,
    partner_code: str = "0",
    flow_code: str = "M,X",
    hs_codes: list[str] | None = None,
    api_key: str | None = None,
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
    headers = {"Accept": "application/json", "User-Agent": "investment-diligence-pipelines/0.1"}
    if api_key:
        headers["Ocp-Apim-Subscription-Key"] = api_key
    uri = f"{api_url}?{urlencode(params)}"
    request = Request(uri, headers=headers)
    context = ssl.create_default_context(cafile=certifi.where())
    with open_url_with_retries(request, timeout=45, context=context) as response:
        payload = response.read()
        status = getattr(response, "status", None)
    return RawCapture(SourceRequest("un_comtrade", uri, {key: str(value) for key, value in params.items()}), payload, status_code=status or 200, adapter_version="un-comtrade-1.0.0")


def load_comtrade_fixture(payload: bytes, *, source_uri: str) -> RawCapture:
    json.loads(payload)  # Fail early with a useful error for malformed fixtures.
    return RawCapture(SourceRequest("un_comtrade_fixture", source_uri), payload, status_code=200, adapter_version="un-comtrade-fixture-1.0.0")


def normalize_trade_flows(payload: bytes, run_id: str, source_record_id: str, hs_codes: set[str] | None = None) -> list[dict]:
    data = json.loads(payload)
    rows = data.get("data", data if isinstance(data, list) else [])
    records = []
    for index, item in enumerate(rows):
        period = str(item.get("period") or item.get("periodDesc") or "")
        hs_code = str(item.get("cmdCode") or item.get("hs_code") or "")
        if not period or not hs_code or (hs_codes and hs_code not in hs_codes):
            continue
        reporter_code = str(item.get("reporterCode") or item.get("reporter_code") or "")
        partner_code = str(item.get("partnerCode") or item.get("partner_code") or "")
        flow = str(item.get("flowDesc") or item.get("flow") or item.get("flowCode") or "").lower()
        value = item.get("primaryValue", item.get("trade_value_usd"))
        if not reporter_code or not partner_code or not flow or value is None:
            continue
        identity = f"{period}|{reporter_code}|{partner_code}|{flow}|{hs_code}|{index}"
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
            "source_record_id": source_record_id,
        })
    return records
