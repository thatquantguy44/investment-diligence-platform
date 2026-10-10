from diligence_pipelines.contracts import Entity


def test_entity_contract_keeps_unknown_time_null():
    entity = Entity(
        record_id="entity:1", entity_id="entity:1", pipeline_id="01_entity_graph",
        source_id="fixture", run_id="run:1", entity_type="organization", canonical_name="Example Co"
    )
    assert entity.first_seen_at is None


def test_entity_rejects_unknown_fields():
    try:
        Entity(
            record_id="entity:1", entity_id="entity:1", pipeline_id="01_entity_graph",
            source_id="fixture", run_id="run:1", entity_type="organization", canonical_name="Example Co", secret="nope"
        )
    except Exception as exc:
        assert "extra" in str(exc)
    else:
        raise AssertionError("unknown fields must be rejected")
