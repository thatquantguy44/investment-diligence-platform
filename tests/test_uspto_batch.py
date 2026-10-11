from pathlib import Path

from diligence_pipelines.sources import iter_bulk_patent_index


def test_batch_iterator_is_bounded():
    records = list(iter_bulk_patent_index(Path("tests/fixtures/patents_bulk.jsonl"), limit=1))
    assert len(records) == 1
    assert records[0]["patent_id"] == "B1"
