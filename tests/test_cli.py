from pathlib import Path

from diligence_pipelines.cli import discover_uspto_odp, refresh_uspto_odp, run_entity_graph, run_multilingual_events, run_public_awards, run_technology_talent, run_trade_exposure, validate_comtrade, validate_gdelt, validate_manifests
from diligence_pipelines.sources.uspto_odp import BulkArtifact
from diligence_pipelines.settings import Settings


def test_manifest_validation():
    assert validate_manifests() == 0


def test_entity_graph_publishes_to_local_storage(tmp_path: Path):
    fixture = Path("tests/fixtures/entity_graph.jsonl")
    assert run_entity_graph(fixture, Settings(data_root=tmp_path)) == 0
    assert list(tmp_path.glob("curated/01_entity_graph/*/entities.jsonl"))
    assert list(tmp_path.glob("raw/synthetic_fixture/*.bin"))


def test_pipeline_02_can_replay_both_sources_offline(tmp_path: Path):
    settings = Settings(data_root=tmp_path)
    assert run_technology_talent(
        "solid state battery", 1,
        Path("tests/fixtures/openalex_works.json"),
        Path("tests/fixtures/patents.json"), None, "auto", settings,
    ) == 0
    assert list(tmp_path.glob("curated/02_technology_talent/*/research_works.jsonl"))
    assert list(tmp_path.glob("curated/02_technology_talent/*/patent_records.jsonl"))


def test_pipeline_03_trade_fixture_publishes_all_outputs(tmp_path: Path):
    assert run_trade_exposure(
        "2024", "842", "0", "M,X", ["850760"],
        Path("tests/fixtures/trade_flows.json"), Settings(data_root=tmp_path),
    ) == 0
    output_root = tmp_path / "curated/03_trade_exposure"
    assert list(output_root.glob("*/trade_flows.jsonl"))
    assert list(output_root.glob("*/partner_concentration.jsonl"))
    assert list(output_root.glob("*/mirror_trade_discrepancies.jsonl"))


def test_pipeline_03_validation_does_not_write_storage(tmp_path: Path, capsys):
    assert validate_comtrade(
        "2024", "842", "0", "M,X", ["850760"],
        Path("tests/fixtures/trade_flows.json"), Settings(data_root=tmp_path),
    ) == 0
    result = __import__("json").loads(capsys.readouterr().out)
    assert result["status"] == "pass"
    assert result["write_mode"] == "none"
    assert result["source_metadata"]["returned_row_count"] > 0
    assert not (tmp_path / "raw").exists()
    assert not (tmp_path / "curated").exists()


def test_odp_release_discovery_persists_snapshot(tmp_path: Path):
    output = tmp_path / "odp-discovery.json"
    assert discover_uspto_odp(
        None, output, Path("tests/fixtures/odp_catalog.json"), Settings(data_root=tmp_path)
    ) == 0
    report = __import__("json").loads(output.read_text())
    assert report["candidate_count"] == 1
    assert (tmp_path / "indexes/uspto_patents/odp_discovery_history.jsonl").exists()


def test_odp_refresh_prepares_release_without_ingesting(tmp_path: Path, monkeypatch):
    selection = tmp_path / "selection.json"
    selection.write_text('{"status": "approved_for_download", "download_url": "https://example.test/patents.jsonl", "reviewer": "analyst", "review_note": "approved"}\n')
    output = tmp_path / "patents.jsonl"
    report_path = tmp_path / "refresh.json"

    def fake_download(url, destination, api_key=None):
        payload = Path("tests/fixtures/patents_bulk.jsonl").read_bytes()
        destination.write_bytes(payload)
        import hashlib
        digest = hashlib.sha256(payload).hexdigest()
        return BulkArtifact(str(destination), url, "2026-10-11T00:00:00+00:00", digest, len(payload), 200)

    monkeypatch.setattr("diligence_pipelines.cli.download_bulk_artifact", fake_download)
    assert refresh_uspto_odp(selection, output, None, report_path, None, None, 10, Settings(data_root=tmp_path)) == 0
    report = __import__("json").loads(report_path.read_text())
    assert report["ingestion_status"] == "not_started"
    assert report["quality"]["status"] == "pass"
    assert output.exists()


def test_pipeline_04_award_fixture_publishes_all_outputs(tmp_path: Path):
    options = {
        "sector": "semiconductors_microelectronics", "award_group": "contracts", "start_date": None, "end_date": None,
        "naics_codes": ["334413"], "psc_codes": [], "keywords": [], "awarding_agencies": [],
        "max_records": 25, "max_transaction_awards": 10, "awards_fixture": Path("tests/fixtures/usaspending_awards.json"),
        "entities": Path("tests/fixtures/entity_graph.jsonl"),
    }
    assert run_public_awards(options, Settings(data_root=tmp_path)) == 0
    output_root = tmp_path / "curated/04_public_awards"
    for name in ("awards", "award_events", "recipient_entities", "technology_program_tags", "recipient_concentration", "obligation_trends", "product_manifest"):
        assert list(output_root.glob(f"*/{name}.jsonl")), name
    manifest = __import__("json").loads(next(output_root.glob("*/product_manifest.jsonl")).read_text())
    assert manifest["record_counts"]["award_events"] == 4
    assert len(manifest["lineage"]) == 3


def test_pipeline_05_event_fixture_publishes_and_validation_does_not_write(tmp_path: Path, capsys):
    options = {
        "sector": None, "query": "", "max_records": 75, "timespan": "7d", "start_datetime": None, "end_datetime": None,
        "source_language": None, "source_country": None, "events_fixture": Path("tests/fixtures/gdelt_artlist.json"),
        "entities": Path("tests/fixtures/entity_graph.jsonl"),
    }
    validation_root = tmp_path / "validation"
    assert validate_gdelt(options, Settings(data_root=validation_root)) == 0
    assert __import__("json").loads(capsys.readouterr().out)["write_mode"] == "none"
    assert not validation_root.exists()
    assert run_multilingual_events(options, Settings(data_root=tmp_path)) == 0
    output_root = tmp_path / "curated/05_multilingual_events"
    for name in ("source_documents", "event_candidates", "entity_event_edges", "event_signal_counts", "product_manifest"):
        assert list(output_root.glob(f"*/{name}.jsonl")), name
    manifest = __import__("json").loads(next(output_root.glob("*/product_manifest.jsonl")).read_text())
    assert manifest["extractor"]["extractor_id"] == "rule_based"


def test_pipeline_01_facts_fixture_publishes_and_validation_does_not_write(tmp_path: Path, capsys):
    from diligence_pipelines.cli import run_sec_facts, validate_sec_facts

    fixture = Path("tests/fixtures/sec_companyfacts.json")
    validation_root = tmp_path / "validation"
    assert validate_sec_facts(["0"], fixture, Settings(data_root=validation_root)) == 0
    assert __import__("json").loads(capsys.readouterr().out)["write_mode"] == "none"
    assert not validation_root.exists()
    assert run_sec_facts(["0"], fixture, Settings(data_root=tmp_path)) == 0
    output_root = tmp_path / "curated/01_entity_graph"
    for name in ("financial_facts", "financial_metrics", "product_manifest"):
        assert list(output_root.glob(f"*/{name}.jsonl")), name
    manifest = __import__("json").loads(next(output_root.glob("*/product_manifest.jsonl")).read_text())
    assert manifest["product_id"] == "company_financials"
    assert manifest["record_counts"] == {"financial_facts": 13, "financial_metrics": 3}
