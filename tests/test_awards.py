import json
from pathlib import Path

import pytest

from diligence_pipelines.awards import award_coverage_report, derive_award_outputs
from diligence_pipelines.entities import load_entity_candidates
from diligence_pipelines.quality import validate_awards
from diligence_pipelines.sources.usaspending import award_search_metadata, build_award_search_body, load_usaspending_fixture, normalize_award_transactions, normalize_awards


FIXTURE = Path("tests/fixtures/usaspending_awards.json")


def _load():
    bundle = load_usaspending_fixture(FIXTURE.read_bytes(), source_uri="file:///fixture")
    awards = normalize_awards(bundle["awards"].payload, "run-1", "source:awards", "contracts")
    events = [event for award_id, capture in bundle["transactions"].items() for event in normalize_award_transactions(capture.payload, award_id, "run-1", "source:tx")]
    return bundle, awards, events


def test_awards_keep_obligation_outlay_and_announcement_separate():
    _, awards, _ = _load()
    first = next(award for award in awards if award["award_display_id"] == "SYN0001")
    assert first["obligated_amount_usd"] == 6000000.0
    assert first["outlay_amount_usd"] == 2500000.0
    assert first["announced_amount_usd"] is None
    assert first["naics_code"] == "334413"
    assert first["source_url"].endswith(first["award_id"])
    plain = next(award for award in awards if award["award_display_id"] == "SYN0003")
    assert (plain["naics_code"], plain["naics_description"]) == ("334413", None)


def test_recipients_group_by_uei_and_concentration_is_reproducible():
    _, awards, events = _load()
    outputs = derive_award_outputs(awards, events, entity_candidates=load_entity_candidates(Path("tests/fixtures/entity_graph.jsonl")))
    acme = next(row for row in outputs["recipient_entities"] if row["recipient_key"] == "uei:SYNUEI000001")
    assert acme["award_count"] == 2
    assert acme["total_obligated_usd"] == 8000000.0
    assert acme["entity_match_candidates"][0]["candidate_entity_id"] == "entity:acme"
    assert acme["entity_match_candidates"][0]["review_status"] == "unreviewed"
    concentration = outputs["recipient_concentration"][0]
    # Shares: 8.0 / 10.5, 2.0 / 10.5, 0.5 / 10.5.
    assert round(concentration["recipient_hhi"], 2) == round((0.8 / 1.05) ** 2 * 10000 + (0.2 / 1.05) ** 2 * 10000 + (0.05 / 1.05) ** 2 * 10000, 2)
    assert concentration["top_recipient_key"] == "uei:SYNUEI000001"
    assert {tag["tag_scheme"] for tag in outputs["technology_program_tags"]} == {"naics", "psc"}


def test_award_coverage_and_quality_flag_missing_history_and_orphans():
    bundle, awards, events = _load()
    metadata = award_search_metadata([bundle["awards"].payload])
    coverage = award_coverage_report(awards, events, metadata, set(bundle["transactions"]))
    assert coverage["awards_with_transaction_history"] == 2
    assert coverage["missing_recipient_uei_count"] == 1
    assert coverage["result_truncated"] is False
    assert all(item.status == "pass" for item in validate_awards(awards, events, coverage, metadata))
    orphan = [{**events[0], "award_event_id": "orphan", "award_id": "missing"}]
    results = {item.check_id: item.status for item in validate_awards(awards, events + orphan, coverage, metadata)}
    assert results["award_event_award_ref_valid"] == "fail"


def test_award_search_body_requires_a_bounding_filter():
    body = build_award_search_body(award_group="contracts", start_date="2024-01-01", end_date="2024-12-31", naics_codes=["334413"], limit=500)
    assert body["filters"]["naics_codes"] == {"require": ["334413"]}
    assert body["filters"]["award_type_codes"] == ["A", "B", "C", "D"]
    assert body["limit"] == 100
    with pytest.raises(ValueError):
        build_award_search_body(award_group="contracts", start_date="2024-01-01", end_date="2024-12-31")


def test_award_search_metadata_reports_truncation_and_errors():
    payload = json.dumps({"results": [{"generated_internal_id": "x"}], "page_metadata": {"hasNext": True}, "messages": ["note"]}).encode()
    metadata = award_search_metadata([payload, json.dumps({"detail": "bad filter"}).encode()])
    assert metadata["returned_row_count"] == 1
    assert metadata["messages"] == ["note"]
    assert metadata["error"] == "bad filter"


class _Response:
    def __init__(self, body: dict):
        self._payload = json.dumps(body).encode()
        self.status = 200

    def read(self):
        return self._payload

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def test_award_search_paginates_until_max_records(monkeypatch):
    from diligence_pipelines.sources import usaspending

    requests = []

    def fake_open(request, **kwargs):
        body = json.loads(request.data)
        requests.append(body)
        rows = [{"generated_internal_id": f"p{body['page']}-{index}"} for index in range(body["limit"])]
        return _Response({"results": rows, "page_metadata": {"page": body["page"], "hasNext": True}})

    monkeypatch.setattr(usaspending, "open_url_with_retries", fake_open)
    captures = usaspending.fetch_award_search(award_group="grants", start_date="2024-01-01", end_date="2024-12-31", keywords=["semiconductor"], max_records=150)
    assert [body["limit"] for body in requests] == [100, 50]
    assert [body["page"] for body in requests] == [1, 2]
    assert requests[0]["filters"]["award_type_codes"] == ["02", "03", "04", "05"]
    assert all(capture.request.source_id == "usaspending" for capture in captures)


SECTORS = Path("config/award_sectors.yaml")
EXPECTED_SECTORS = {"semiconductors_microelectronics", "aerospace_missiles_space", "defense_electronics_sensing", "defense_rd", "ai_cyber_software"}


def test_every_sector_preset_builds_a_bounded_search():
    import yaml

    from diligence_pipelines.awards import load_award_sector

    names = set(yaml.safe_load(SECTORS.read_text())["sectors"])
    assert names == EXPECTED_SECTORS
    for name in names:
        sector = load_award_sector(name, SECTORS)
        assert all(code.isdigit() and len(code) == 6 for code in sector["naics"]), name
        body = build_award_search_body(award_group=sector["award_group"], start_date="2024-01-01", end_date="2024-12-31", naics_codes=sector["naics"], psc_codes=sector["psc"], keywords=sector["keywords"])
        assert body["filters"]["naics_codes"]["require"] == sector["naics"]
    assert load_award_sector("ai_cyber_software", SECTORS)["keywords"]
    with pytest.raises(ValueError, match="choose from"):
        load_award_sector("shipbuilding", SECTORS)


def test_awarding_agency_filter_targets_top_tier_awarding_agency():
    body = build_award_search_body(award_group="contracts", start_date="2024-01-01", end_date="2024-12-31", naics_codes=["334511"], awarding_agencies=["Department of Defense"])
    assert body["filters"]["agencies"] == [{"type": "awarding", "tier": "toptier", "name": "Department of Defense"}]


def test_cli_merges_sector_preset_with_explicit_filters(monkeypatch):
    import sys

    from diligence_pipelines import cli

    captured = {}
    monkeypatch.setattr(cli, "validate_usaspending", lambda options, settings: captured.update(options) or 0)
    monkeypatch.setattr(sys, "argv", ["diligence-pipelines", "validate-usaspending", "--sector", "defense_electronics_sensing", "--naics", "334290", "--awarding-agency", "Department of Defense", "--start-date", "2024-01-01", "--end-date", "2024-12-31"])
    assert cli.main() == 0
    assert captured["naics_codes"] == ["334511", "334220", "334290"]
    assert captured["award_group"] == "contracts"
    assert captured["awarding_agencies"] == ["Department of Defense"]
    assert captured["sector"] == "defense_electronics_sensing"
