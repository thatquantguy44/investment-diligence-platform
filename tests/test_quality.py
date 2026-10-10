from diligence_pipelines.contracts import Entity
from diligence_pipelines.quality import validate_entities


def make_entity(entity_id: str) -> Entity:
    return Entity(record_id=entity_id, entity_id=entity_id, pipeline_id="p", source_id="s", run_id="r", entity_type="organization", canonical_name=entity_id)


def test_duplicate_entity_ids_block_publication():
    results = validate_entities([make_entity("same"), make_entity("same")])
    assert next(result for result in results if result.check_id == "identifier_unique").status == "fail"
