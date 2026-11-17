import csv
import json

import pytest

from diligence_pipelines.fundcomb_manual import load_manual_profiles, write_manual_map


FIELDS = [
    "investor_name", "profile_url", "headquarters_country", "focus_area",
    "evidence_excerpt", "evidence_kind", "observed_on",
]


def write_csv(path, rows):
    with path.open("w", newline="") as destination:
        writer = csv.DictWriter(destination, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def example_row(**overrides):
    row = {
        "investor_name": "Synthetic Sensor Capital",
        "profile_url": "https://www.fundcomb.com/funds/synthetic-sensor-capital",
        "headquarters_country": "Singapore",
        "focus_area": "sensors",
        "evidence_excerpt": "Synthetic fixture: invests in sensor components.",
        "evidence_kind": "profile_description",
        "observed_on": "2026-11-17",
    }
    return {**row, **overrides}


def test_manual_map_marks_sample_and_absent_themes_as_coverage_gap(tmp_path):
    source = tmp_path / "profiles.csv"
    write_csv(source, [example_row(), example_row(focus_area="maritime_systems")])
    report = write_manual_map(source, tmp_path / "output")
    rows = [json.loads(line) for line in (tmp_path / "output/investor_focus_observations.jsonl").read_text().splitlines()]

    assert report["distinct_investor_count"] == 1
    assert report["focus_counts"] == {"maritime_systems": 1, "semiconductors": 0, "sensors": 1}
    assert report["status"] == "research_sample_only"
    assert rows[0]["signal_type"] == "profile_claim"
    assert rows[0]["review_status"] == "unreviewed"
    assert rows[0]["profile_url"] == "https://fundcomb.com/funds/synthetic-sensor-capital"
    assert "not zero market activity" in report["limitations"][2]


@pytest.mark.parametrize("change", [
    {"profile_url": "http://fundcomb.com/funds/synthetic-sensor-capital"},
    {"profile_url": "https://fundcomb.com.evil.example/funds/synthetic-sensor-capital"},
    {"profile_url": "https://fundcomb.com/funds/synthetic-sensor-capital?key=secret"},
    {"focus_area": "unreviewed_sector"},
    {"evidence_excerpt": ""},
    {"observed_on": "2099-01-01"},
])
def test_manual_map_rejects_invalid_observations(tmp_path, change):
    source = tmp_path / "profiles.csv"
    write_csv(source, [example_row(**change)])
    with pytest.raises(ValueError):
        load_manual_profiles(source)


def test_manual_map_rejects_duplicate_profile_focus(tmp_path):
    source = tmp_path / "profiles.csv"
    write_csv(source, [example_row(), example_row(investor_name="Different name")])
    with pytest.raises(ValueError, match="duplicate"):
        load_manual_profiles(source)
