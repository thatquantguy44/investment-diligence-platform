from pathlib import Path

from diligence_pipelines.sources import load_bulk_patent_index


def test_bulk_index_normalizes_records_and_source_checksum():
    records, metadata = load_bulk_patent_index(Path("tests/fixtures/patents_bulk.jsonl"))
    assert len(records) == 2
    assert records[0]["patent_id"] == "B1"
    assert records[0]["assignee_name"] == "Example Energy"
    assert len(metadata["source_file_sha256"]) == 64
    assert metadata["skipped_count"] == 0


def test_bulk_index_reads_tsv_zip_and_honors_limit(tmp_path):
    import zipfile

    source = tmp_path / "patents.tsv.zip"
    with zipfile.ZipFile(source, "w") as archive:
        archive.writestr("patents.tsv", "patent_id\tpatent_title\n1\tFirst\n2\tSecond\n")
    records, metadata = load_bulk_patent_index(source, limit=1)
    assert len(records) == 1
    assert records[0]["patent_id"] == "1"
    assert metadata["limit"] == 1
