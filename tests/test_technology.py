from diligence_pipelines.technology import derive_topic_observation


def test_topic_observation_has_reproducible_formula_and_inputs():
    records = [
        {"record_id": "research_work:1", "publication_date": "2022-01-01"},
        {"record_id": "research_work:2", "publication_date": "2024-01-01"},
    ]
    observation = derive_topic_observation(records, "battery", "run-1")
    assert observation["value"] == 2.0
    assert observation["formula_version"] == "research_work_count.v1"
    assert observation["input_record_ids"] == ["research_work:1", "research_work:2"]
