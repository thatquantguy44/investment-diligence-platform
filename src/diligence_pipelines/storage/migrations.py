"""Small, dependency-free PostgreSQL migration runner for additive schema changes."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Migration:
    migration_id: str
    description: str
    sql: str


MIGRATIONS = (
    Migration(
        "0001_patent_catalog_materializations",
        "Record auditable patent-catalog materialization runs.",
        """
        CREATE TABLE IF NOT EXISTS diligence.patent_catalog_materializations (
            materialization_id uuid PRIMARY KEY,
            started_at timestamptz NOT NULL,
            completed_at timestamptz NOT NULL,
            status text NOT NULL CHECK (status IN ('completed', 'completed_with_mismatch')),
            index_row_count bigint NOT NULL,
            catalog_row_count bigint NOT NULL,
            parity_mismatch_count bigint NOT NULL,
            upserted_row_count bigint NOT NULL,
            source_file_sha256s jsonb NOT NULL
        )
        """,
    ),
    Migration(
        "0002_uspto_odp_refresh_history",
        "Persist approved USPTO ODP refresh outcomes for operations and alerting.",
        """
        CREATE TABLE IF NOT EXISTS diligence.uspto_odp_refreshes (
            refresh_id uuid PRIMARY KEY,
            status text NOT NULL CHECK (status IN ('prepared', 'blocked', 'failed')),
            report jsonb NOT NULL,
            refreshed_at timestamptz NOT NULL
        )
        """,
    ),
)


def apply_postgres_migrations(connection) -> list[str]:
    """Apply known additive migrations exactly once and return newly applied IDs."""
    with connection.cursor() as cursor:
        cursor.execute("CREATE SCHEMA IF NOT EXISTS diligence")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS diligence.schema_migrations (
                migration_id text PRIMARY KEY,
                description text NOT NULL,
                applied_at timestamptz NOT NULL DEFAULT now()
            )
        """)
        cursor.execute("LOCK TABLE diligence.schema_migrations IN EXCLUSIVE MODE")
        cursor.execute("SELECT migration_id FROM diligence.schema_migrations")
        applied = {row[0] for row in cursor.fetchall()}
        newly_applied = []
        for migration in MIGRATIONS:
            if migration.migration_id in applied:
                continue
            cursor.execute(migration.sql)
            cursor.execute(
                "INSERT INTO diligence.schema_migrations (migration_id, description) VALUES (%s, %s)",
                (migration.migration_id, migration.description),
            )
            newly_applied.append(migration.migration_id)
    connection.commit()
    return newly_applied
