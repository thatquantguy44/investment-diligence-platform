from pathlib import Path

from diligence_pipelines.sources.uspto_bulk import fetch_patents_from_bulk_file


def test_bulk_search_returns_matching_patents():
    capture = fetch_patents_from_bulk_file(Path("tests/fixtures/patents_bulk.jsonl"), "solid state battery", max_results=1)
    assert capture.request.source_id == "uspto_patents_bulk"
    assert capture.status_code == 200
    assert b"B1" in capture.payload
    assert b"B2" not in capture.payload
