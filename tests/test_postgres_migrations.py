from diligence_pipelines.storage.migrations import MIGRATIONS


def test_postgres_migrations_have_unique_ascending_ids():
    migration_ids = [migration.migration_id for migration in MIGRATIONS]
    assert migration_ids == sorted(migration_ids)
    assert len(migration_ids) == len(set(migration_ids))
    assert "patent_catalog_materializations" in MIGRATIONS[0].sql
    assert "uspto_odp_refreshes" in MIGRATIONS[1].sql
