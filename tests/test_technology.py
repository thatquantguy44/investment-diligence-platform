from diligence_pipelines.technology import derive_institution_edges, derive_topic_observation


def test_topic_observation_has_reproducible_formula_and_inputs():
    records = [
        {"record_id": "research_work:1", "publication_date": "2022-01-01"},
        {"record_id": "research_work:2", "publication_date": "2024-01-01"},
    ]
    observation = derive_topic_observation(records, "battery", "run-1")
    assert observation["value"] == 2.0
    assert observation["formula_version"] == "research_work_count.v1"
    assert observation["input_record_ids"] == ["research_work:1", "research_work:2"]


def test_institution_edges_preserve_affiliation_limitation():
    records = [{"work_id": "W1", "source_record_id": "source:1", "institutions": [{"id": "I1", "name": "Example University"}]}]
    edges = derive_institution_edges(records, "run-1")
    assert edges[0]["relationship_type"] == "authorship_affiliation"
    assert "not evidence of employment" in edges[0]["limitations"][0]
