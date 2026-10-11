import json
from pathlib import Path

from diligence_pipelines.sources.uspto_release import compare_bulk_releases, profile_bulk_release


def test_profile_bulk_release_reports_schema_and_coverage():
    report = profile_bulk_release(Path("tests/fixtures/patents_bulk.jsonl"))
    assert report["status"] == "pass"
    assert report["schema_status"] == "pass"
    assert report["coverage"]["normalized_rate"] == 1.0


def test_compare_bulk_releases_reports_new_changed_removed(tmp_path: Path):
    previous = tmp_path / "previous.jsonl"
    current = tmp_path / "current.jsonl"
    previous.write_text(json.dumps({"patent_id": "A", "title": "old"}) + "\n" + json.dumps({"patent_id": "B", "title": "same"}) + "\n")
    current.write_text(json.dumps({"patent_id": "A", "title": "changed"}) + "\n" + json.dumps({"patent_id": "C", "title": "new"}) + "\n")
    report = compare_bulk_releases(previous, current)
    assert report["new_count"] == 1
    assert report["changed_count"] == 1
    assert report["removed_count"] == 1
