import json
from datetime import datetime, timedelta, timezone
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


def test_profile_marks_old_but_allowed_patent_data_for_review(tmp_path: Path):
    path = tmp_path / "patents.jsonl"
    patent_date = (datetime.now(timezone.utc).date() - timedelta(days=298)).isoformat()
    path.write_text(json.dumps({"patent_id": "A", "patent_title": "Example", "patent_date": patent_date}) + "\n")

    report = profile_bulk_release(path, max_age_days=330, warning_age_days=240)

    assert report["status"] == "pass"
    assert report["freshness_status"] == "stale_review_required"
    assert report["freshness_days"] == 298


def test_profile_blocks_unknown_and_future_patent_dates(tmp_path: Path):
    path = tmp_path / "patents.jsonl"
    for patent_date in (None, (datetime.now(timezone.utc).date() + timedelta(days=1)).isoformat()):
        path.write_text(json.dumps({"patent_id": "A", "patent_title": "Example", "patent_date": patent_date}) + "\n")
        report = profile_bulk_release(path, max_age_days=330, warning_age_days=240)
        assert report["status"] == "fail"
        assert report["freshness_status"] == "fail"


def test_profile_blocks_patent_data_past_hard_limit(tmp_path: Path):
    path = tmp_path / "patents.jsonl"
    patent_date = (datetime.now(timezone.utc).date() - timedelta(days=331)).isoformat()
    path.write_text(json.dumps({"patent_id": "A", "patent_title": "Example", "patent_date": patent_date}) + "\n")

    report = profile_bulk_release(path, max_age_days=330, warning_age_days=240)

    assert report["status"] == "fail"
    assert report["freshness_status"] == "fail"
