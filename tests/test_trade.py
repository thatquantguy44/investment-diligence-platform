import json
from pathlib import Path

from diligence_pipelines.sources.comtrade import comtrade_response_metadata, normalize_trade_flows
from diligence_pipelines.trade import coverage_report, derive_trade_outputs


def test_trade_metrics_are_reproducible():
    payload = Path("tests/fixtures/trade_flows.json").read_bytes()
    records = normalize_trade_flows(payload, "run-1", "source:trade", {"850760"})
    outputs = derive_trade_outputs(records)
    concentration = next(row for row in outputs["partner_concentration"] if row["reporter_code"] == "842" and row["flow"] == "export")
    assert round(concentration["hhi"], 2) == 5555.56
    assert len(outputs["mirror_trade_discrepancies"]) == 2
    assert coverage_report(records, outputs, {"850760"})["missingness_rate"] == 0.0


def test_trade_normalization_accepts_fixture_shape():
    payload = json.dumps({"data": [{"period": "2024", "reporterCode": "1", "partnerCode": "2", "flowCode": "M", "flowDesc": "Import", "cmdCode": "01", "primaryValue": 12}]}).encode()
    records = normalize_trade_flows(payload, "run-1", "source:trade")
    assert records[0]["trade_value_usd"] == 12.0


def test_trade_response_metadata_captures_vintage_and_revision_fields():
    payload = json.dumps({"count": 1, "data": [{"cmdCode": "850760", "dataVersion": "2026-01", "isOriginal": True}]}).encode()
    metadata = comtrade_response_metadata(payload)
    assert metadata["response_count"] == 1
    assert metadata["returned_row_count"] == 1
    assert metadata["source_vintages"] == ["2026-01"]
    assert metadata["revision_fields_present"] == ["dataVersion", "isOriginal"]


def test_trade_normalization_preserves_zero_world_partner_code():
    payload = json.dumps({"data": [{"period": "2024", "reporterCode": 842, "partnerCode": 0, "flowCode": "M", "cmdCode": "850760", "primaryValue": 12}]}).encode()
    records = normalize_trade_flows(payload, "run-1", "source:trade", {"850760"})
    assert records[0]["partner_code"] == "0"
