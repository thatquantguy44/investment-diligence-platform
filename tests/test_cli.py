from pathlib import Path

from diligence_pipelines.cli import run_entity_graph, run_technology_talent, validate_manifests
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
