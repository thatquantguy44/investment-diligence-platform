from pathlib import Path

from diligence_pipelines.cli import run_entity_graph, validate_manifests
from diligence_pipelines.settings import Settings


def test_manifest_validation():
    assert validate_manifests() == 0


def test_entity_graph_publishes_to_local_storage(tmp_path: Path):
    fixture = Path("tests/fixtures/entity_graph.jsonl")
    assert run_entity_graph(fixture, Settings(data_root=tmp_path)) == 0
    assert list(tmp_path.glob("curated/01_entity_graph/*/entities.jsonl"))
    assert list(tmp_path.glob("raw/synthetic_fixture/*.bin"))
