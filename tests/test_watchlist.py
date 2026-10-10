from pathlib import Path

from diligence_pipelines.cli import load_watchlist
from diligence_pipelines.sources.gleif import normalize_gleif_alias, normalize_lei


def test_watchlist_deduplicates_ciks(tmp_path: Path):
    path = tmp_path / "watchlist.yaml"
    path.write_text("entities:\n  - cik: '320193'\n  - cik: '320193'\n  - cik: '789019'\n")
    assert [item["cik"] for item in load_watchlist(path)] == ["320193", "789019"]


def test_lei_validation_and_alias_normalization():
    lei = "5493001KJTIIGC8Y1R12"
    assert normalize_lei(lei) == lei
    payload = ("{\"data\":{\"id\":\"" + lei + "\",\"attributes\":{\"entity\":{\"legalName\":{\"name\":\"Example Holdings Ltd\"}}}}}").encode()
    alias = normalize_gleif_alias(payload, "run-1", "entity:sec:0000000001")
    assert alias["match_method"] == "lei_exact"
    assert alias["review_status"] == "accepted"
