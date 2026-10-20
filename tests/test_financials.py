import json
from pathlib import Path

import pytest

from diligence_pipelines.financials import derive_financial_metrics, financial_coverage_report
from diligence_pipelines.quality import validate_financial_facts
from diligence_pipelines.sources.sec import normalize_financial_facts, sec_facts_metadata


FIXTURE = Path("tests/fixtures/sec_companyfacts.json")


def _facts():
    return normalize_financial_facts(FIXTURE.read_bytes(), "run-1", "source:sec")


def test_facts_keep_every_filing_and_drop_quarterly_and_uncollected_concepts():
    facts = _facts()
    assert {fact["form"] for fact in facts} == {"10-K"}
    assert "AccountsPayableCurrent" not in {fact["concept"] for fact in facts}
    revenue_2023 = [fact for fact in facts if fact["concept"] == "Revenues" and fact["period_end"] == "2023-12-31"]
    assert sorted(fact["value"] for fact in revenue_2023) == [1150000000.0, 1200000000.0]  # original and restated both retained
    assert {fact["entity_id"] for fact in facts} == {"entity:sec:0000999001"}
    first = revenue_2023[0]
    assert first["filing_index_url"].startswith("https://www.sec.gov/Archives/edgar/data/999001/")
    assert first["fiscal_year_reported"] is not None and first["filed_at"]


def test_metrics_use_latest_filed_values_and_flag_restatements():
    metrics = {row["period_end"]: row for row in derive_financial_metrics(_facts())}
    assert set(metrics) == {"2022-12-31", "2023-12-31", "2024-12-31"}
    assert metrics["2023-12-31"]["revenue_usd"] == 1150000000.0
    assert metrics["2023-12-31"]["restated"] is True
    assert metrics["2023-12-31"]["as_of_filed"] == "2025-02-19"
    assert metrics["2024-12-31"]["restated"] is False
    assert round(metrics["2024-12-31"]["rd_intensity"], 6) == 0.18
    assert round(metrics["2024-12-31"]["capex_intensity"], 6) == 0.06
    assert round(metrics["2024-12-31"]["operating_margin"], 6) == 0.15
    assert round(metrics["2024-12-31"]["revenue_growth_yoy"], 6) == round(1.5 / 1.15 - 1, 6)
    assert metrics["2022-12-31"]["revenue_growth_yoy"] is None  # no prior year
    assert metrics["2022-12-31"]["capex_intensity"] is None  # capex not reported that year
    assert metrics["2024-12-31"]["total_assets_usd"] == 2400000000.0


def test_ratios_are_null_when_denominator_is_not_positive():
    payload = json.loads(FIXTURE.read_bytes())
    for row in payload["facts"]["us-gaap"]["Revenues"]["units"]["USD"]:
        row["val"] = 0 if row["end"] == "2024-12-31" else row["val"]
    metrics = {row["period_end"]: row for row in derive_financial_metrics(normalize_financial_facts(json.dumps(payload).encode(), "r", "s"))}
    assert metrics["2024-12-31"]["rd_intensity"] is None
    assert metrics["2024-12-31"]["revenue_growth_yoy"] == -1.0  # prior base is positive, so a drop to zero is a real -100%

    for row in payload["facts"]["us-gaap"]["Revenues"]["units"]["USD"]:
        row["val"] = 0 if row["end"] == "2023-12-31" else row["val"]
    zero_base = {row["period_end"]: row for row in derive_financial_metrics(normalize_financial_facts(json.dumps(payload).encode(), "r", "s"))}
    assert zero_base["2024-12-31"]["revenue_growth_yoy"] is None  # growth from a zero base is undefined


def test_quality_passes_fixture_and_catches_future_dated_and_orphan_inputs():
    facts = _facts()
    metrics = derive_financial_metrics(facts)
    metadata = {"0000999001": sec_facts_metadata(FIXTURE.read_bytes())}
    coverage = financial_coverage_report(facts, metrics, metadata, ["0000999001"])
    assert coverage["restated_period_count"] == 1
    assert coverage["missing_concept_groups_by_cik"]["0000999001"] == []
    assert all(item.status == "pass" for item in validate_financial_facts(facts, metrics, coverage, metadata))
    early = [{**facts[0], "fact_id": "x", "filed_at": "1999-01-01"}]
    assert {item.check_id: item.status for item in validate_financial_facts(facts + early, metrics, coverage, metadata)}["financial_fact_filed_after_period"] == "fail"
    orphaned = [{**metrics[0], "input_fact_ids": ["missing"]}]
    assert {item.check_id: item.status for item in validate_financial_facts(facts, orphaned, coverage, metadata)}["financial_metric_inputs_traceable"] == "fail"
    bad = {"0000999001": sec_facts_metadata(b"Not Found")}
    assert {item.check_id: item.status for item in validate_financial_facts([], [], coverage, bad)}["financial_source_metadata_present"] == "fail"


def test_sec_facts_fetch_uses_companyfacts_endpoint(monkeypatch):
    from diligence_pipelines.sources import sec

    seen = {}

    class _Response:
        status = 200
        headers = {}

        def read(self):
            return b"{}"

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    def fake_open(request, **kwargs):
        seen["uri"] = request.full_url
        seen["agent"] = request.headers["User-agent"]
        return _Response()

    monkeypatch.setattr(sec, "open_url_with_retries", fake_open)
    capture = sec.fetch_sec_companyfacts("320193", "tests/1.0 test@example.com")
    assert seen["uri"] == "https://data.sec.gov/api/xbrl/companyfacts/CIK0000320193.json"
    assert seen["agent"] == "tests/1.0 test@example.com"
    assert capture.request.source_id == "sec_edgar"
    with pytest.raises(ValueError):
        sec.fetch_sec_companyfacts("abc", "x")
