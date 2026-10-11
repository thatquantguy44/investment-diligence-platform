from diligence_pipelines.storage.local import LocalStorage


def test_local_patent_index_search(tmp_path):
    storage = LocalStorage(tmp_path)
    storage.upsert_patent_index([
        {"patent_id": "1", "title": "Solid state battery", "abstract": "Ceramic separator", "assignee_name": "Example Energy"},
        {"patent_id": "2", "title": "Optical sensor", "abstract": "Light detection", "assignee_name": "Example Sensors"},
    ], {"source_file_sha256": "x", "source_path": "fixture"})
    results = storage.search_patent_index("solid state battery", limit=5)
    assert [item["patent_id"] for item in results] == ["1"]
