from pathlib import Path

from diligence_pipelines.entities import find_entity_mentions, load_entity_candidates
from diligence_pipelines.events import RuleBasedEventExtractor, derive_event_outputs, event_coverage_report
from diligence_pipelines.quality import validate_event_candidates
from diligence_pipelines.sources.gdelt import canonical_url, gdelt_response_metadata, normalize_gdelt_articles, parse_gdelt_payload


FIXTURE = Path("tests/fixtures/gdelt_artlist.json")
ENTITIES = Path("tests/fixtures/entity_graph.jsonl")


def _derive():
    payload = FIXTURE.read_bytes()
    documents = normalize_gdelt_articles(payload, "run-1", "source:gdelt")
    outputs = derive_event_outputs(documents, RuleBasedEventExtractor(), entity_candidates=load_entity_candidates(ENTITIES), content_sha256="abc")
    return payload, documents, outputs


def test_documents_deduplicate_urls_and_mark_syndicated_copies():
    _, documents, _ = _derive()
    assert len(documents) == 5  # tracking-parameter and www variants collapse to one URL
    duplicates = [document for document in documents if document["duplicate_of"]]
    assert len(duplicates) == 1
    assert duplicates[0]["domain"] == "syndicate.example.test"
    assert documents[0]["first_seen_at"] == "2024-10-15T12:00:00+00:00"
    assert documents[0]["published_at"] is None
    assert canonical_url("https://WWW.Example.test/a/?utm_source=x&id=7") == "https://example.test/a?id=7"


def test_rule_extractor_returns_exact_spans_and_links_entities():
    _, documents, outputs = _derive()
    types = {(row["document_id"], row["event_type"]) for row in outputs["event_candidates"]}
    by_title = {document["title"]: document["document_id"] for document in documents}
    assert (by_title["Acme Robotics raises $50 million in Series B funding round"], "funding_round") in types
    assert (by_title["Delta Materials breaks ground on new plant for silicon carbide wafers"], "facility") in types
    assert (by_title["Delta Materials 宣布收购一家晶圆厂"], "acquisition") in types
    assert all(row["status"] == "candidate" and row["event_time"] is None for row in outputs["event_candidates"])
    assert {edge["entity_id"] for edge in outputs["entity_event_edges"]} == {"entity:acme", "entity:delta"}
    funding = next(row for row in outputs["event_signal_counts"] if row["entity_id"] == "entity:acme" and row["event_type"] == "funding_round")
    assert funding["candidate_count"] == 1
    assert funding["distinct_domain_count"] == 2  # original plus syndicated copy


def test_event_quality_passes_fixture_and_rejects_unsupported_excerpts():
    payload, documents, outputs = _derive()
    metadata = gdelt_response_metadata(payload)
    coverage = event_coverage_report(documents, outputs, metadata)
    assert coverage["documents_without_candidates"] == 1
    assert all(item.status == "pass" for item in validate_event_candidates(documents, outputs["event_candidates"], coverage, metadata))
    tampered = [{**outputs["event_candidates"][0], "evidence": {**outputs["event_candidates"][0]["evidence"], "quote_or_excerpt": "acquires rival"}}]
    results = {item.check_id: item.status for item in validate_event_candidates(documents, tampered, coverage, metadata)}
    assert results["event_evidence_supported"] == "fail"
    promoted = [{**outputs["event_candidates"][0], "status": "verified"}]
    assert {item.check_id: item.status for item in validate_event_candidates(documents, promoted, coverage, metadata)}["event_candidates_unverified"] == "fail"


def test_gdelt_plain_text_errors_are_reported_not_parsed():
    articles, error = parse_gdelt_payload(b"Your search contained a phrase that was too short.")
    assert articles == []
    assert error.startswith("Your search")
    assert parse_gdelt_payload(b"{}") == ([], None)


def test_entity_mentions_strip_legal_suffixes_and_respect_word_boundaries():
    candidates = [("entity:acme", "Acme Robotics Pte. Ltd."), ("entity:co", "Co")]
    mentions = find_entity_mentions("ACME ROBOTICS wins contract; Acmerobotics unrelated", candidates)
    assert [mention["entity_id"] for mention in mentions] == ["entity:acme"]
    assert find_entity_mentions("Acme Roboticsville opens", candidates) == []


def test_gdelt_fetch_builds_bounded_artlist_query(monkeypatch):
    from urllib.parse import parse_qs, urlsplit

    from diligence_pipelines.sources import gdelt

    seen = {}

    class _Response:
        status = 200

        def read(self):
            return b'{"articles": []}'

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    def fake_open(request, **kwargs):
        seen.update(parse_qs(urlsplit(request.full_url).query))
        return _Response()

    monkeypatch.setattr(gdelt, "open_url_with_retries", fake_open)
    capture = gdelt.fetch_gdelt_articles("\"silicon carbide\"", max_records=1000, source_language="english", start_datetime="20241001000000", end_datetime="20241031000000")
    assert seen["query"] == ["\"silicon carbide\" sourcelang:english"]
    assert seen["maxrecords"] == ["250"]
    assert seen["mode"] == ["artlist"] and "timespan" not in seen
    assert capture.request.source_id == "gdelt_doc"


def test_award_recipients_can_seed_event_entity_edges(tmp_path):
    import json

    from diligence_pipelines.awards import derive_award_outputs
    from diligence_pipelines.sources.usaspending import load_usaspending_fixture, normalize_awards

    bundle = load_usaspending_fixture(Path("tests/fixtures/usaspending_awards.json").read_bytes(), source_uri="file:///fixture")
    awards = normalize_awards(bundle["awards"].payload, "run-1", "source:awards", "contracts")
    recipients = derive_award_outputs(awards, [])["recipient_entities"]
    path = tmp_path / "recipient_entities.jsonl"
    path.write_text("".join(json.dumps(row) + "\n" for row in recipients))
    candidates = load_entity_candidates(path)
    assert ("uei:SYNUEI000001", "ACME ROBOTICS PTE LTD") in candidates
    documents = normalize_gdelt_articles(FIXTURE.read_bytes(), "run-1", "source:gdelt")
    outputs = derive_event_outputs(documents, RuleBasedEventExtractor(), entity_candidates=candidates, content_sha256="abc")
    assert {edge["entity_id"] for edge in outputs["entity_event_edges"]} == {"uei:SYNUEI000001", "uei:SYNUEI000002"}


def test_event_query_presets_match_award_sectors_and_compose_with_query(monkeypatch):
    import sys

    import yaml

    from diligence_pipelines import cli
    from diligence_pipelines.events import load_event_query

    award_sectors = set(yaml.safe_load(Path("config/award_sectors.yaml").read_text())["sectors"])
    event_sectors = set(yaml.safe_load(Path("config/event_queries.yaml").read_text())["sectors"])
    assert event_sectors == award_sectors
    for name in event_sectors:
        query = load_event_query(name, Path("config/event_queries.yaml"))
        assert query.count("(") == query.count(")") and query.count('"') % 2 == 0, name

    captured = {}
    monkeypatch.setattr(cli, "validate_gdelt", lambda options, settings: captured.update(options) or 0)
    monkeypatch.setattr(sys, "argv", ["diligence-pipelines", "validate-gdelt", "--sector", "defense_rd", "--query", "Anduril"])
    assert cli.main() == 0
    assert captured["query"] == load_event_query("defense_rd", Path("config/event_queries.yaml")) + " Anduril"
    assert captured["sector"] == "defense_rd"
