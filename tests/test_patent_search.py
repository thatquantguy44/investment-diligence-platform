from diligence_pipelines.storage.local import LocalStorage


def test_local_patent_index_search(tmp_path):
    storage = LocalStorage(tmp_path)
    storage.upsert_patent_index([
        {"patent_id": "1", "title": "Solid state battery", "abstract": "Ceramic separator", "assignee_name": "Example Energy"},
        {"patent_id": "2", "title": "Optical sensor", "abstract": "Light detection", "assignee_name": "Example Sensors"},
    ], {"source_file_sha256": "x", "source_path": "fixture"})
    results = storage.search_patent_index("solid state battery", limit=5)
    assert [item["patent_id"] for item in results] == ["1"]


def test_local_patent_catalog_is_deduplicated(tmp_path):
    storage = LocalStorage(tmp_path)
    record = {"patent_id": "1", "title": "Solid state battery"}
    storage.upsert_patent_catalog([record], "release-a")
    storage.upsert_patent_catalog([{**record, "title": "Updated solid state battery"}], "release-b")
    rows = [__import__("json").loads(line) for line in (tmp_path / "indexes/uspto_patents/patent_catalog.jsonl").read_text().splitlines()]
    assert len(rows) == 1
    assert rows[0]["record"]["title"] == "Updated solid state battery"
    assert rows[0]["source_file_sha256"] == "release-b"
