from __future__ import annotations

import json
from typing import Any

from diligence_pipelines.sources.base import RawCapture


class PostgresStorage:
    """PostgreSQL storage adapter for raw captures and curated Pipeline 01 output."""

    def __init__(self, dsn: str):
        self.dsn = dsn
        self._connection = None

    def _connect(self):
        if self._connection is None:
            try:
                import psycopg
            except ImportError as exc:
                raise RuntimeError("Install PostgreSQL support with: pip install -e '.[postgres]'") from exc
            self._connection = psycopg.connect(self.dsn)
        return self._connection

    def initialize(self) -> None:
        connection = self._connect()
        with connection.cursor() as cursor:
            cursor.execute("CREATE SCHEMA IF NOT EXISTS diligence")
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS diligence.raw_captures (
                    content_sha256 text PRIMARY KEY,
                    source_id text NOT NULL,
                    source_uri text NOT NULL,
                    params jsonb NOT NULL,
                    retrieved_at timestamptz NOT NULL,
                    status_code integer,
                    adapter_version text NOT NULL,
                    payload bytea NOT NULL
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS diligence.entities (
                    entity_id text NOT NULL,
                    run_id uuid NOT NULL,
                    record jsonb NOT NULL,
                    created_at timestamptz NOT NULL DEFAULT now(),
                    PRIMARY KEY (entity_id, run_id)
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS diligence.product_manifests (
                    materialization_id uuid PRIMARY KEY,
                    product_id text NOT NULL,
                    pipeline_id text NOT NULL,
                    manifest jsonb NOT NULL,
                    created_at timestamptz NOT NULL DEFAULT now()
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS diligence.entity_aliases (
                    record_id text NOT NULL,
                    run_id uuid NOT NULL,
                    entity_id text NOT NULL,
                    record jsonb NOT NULL,
                    PRIMARY KEY (record_id, run_id)
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS diligence.match_candidates (
                    candidate_id text NOT NULL,
                    run_id uuid NOT NULL,
                    candidate_entity_id text NOT NULL,
                    record jsonb NOT NULL,
                    PRIMARY KEY (candidate_id, run_id)
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS diligence.research_works (
                    work_id text NOT NULL,
                    run_id uuid NOT NULL,
                    record jsonb NOT NULL,
                    created_at timestamptz NOT NULL DEFAULT now(),
                    PRIMARY KEY (work_id, run_id)
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS diligence.technology_topic_observations (
                    observation_id text NOT NULL,
                    run_id uuid NOT NULL,
                    record jsonb NOT NULL,
                    created_at timestamptz NOT NULL DEFAULT now(),
                    PRIMARY KEY (observation_id, run_id)
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS diligence.patent_records (
                    patent_id text NOT NULL,
                    run_id uuid NOT NULL,
                    record jsonb NOT NULL,
                    created_at timestamptz NOT NULL DEFAULT now(),
                    PRIMARY KEY (patent_id, run_id)
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS diligence.patent_assignments (
                    record_id text NOT NULL,
                    run_id uuid NOT NULL,
                    record jsonb NOT NULL,
                    PRIMARY KEY (record_id, run_id)
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS diligence.inventor_edges (
                    record_id text NOT NULL,
                    run_id uuid NOT NULL,
                    record jsonb NOT NULL,
                    PRIMARY KEY (record_id, run_id)
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS diligence.institution_edges (
                    record_id text NOT NULL,
                    run_id uuid NOT NULL,
                    record jsonb NOT NULL,
                    PRIMARY KEY (record_id, run_id)
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS diligence.patent_index (
                    patent_id text PRIMARY KEY,
                    source_file_sha256 text NOT NULL,
                    record jsonb NOT NULL,
                    search_text text NOT NULL,
                    ingested_at timestamptz NOT NULL DEFAULT now()
                )
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS patent_index_search_idx ON diligence.patent_index USING gin (to_tsvector('simple', search_text))")
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS diligence.patent_index_runs (
                    source_file_sha256 text PRIMARY KEY,
                    source_path text NOT NULL,
                    metadata jsonb NOT NULL,
                    ingested_at timestamptz NOT NULL DEFAULT now()
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS diligence.patent_enrichment_staging (
                    source_file_sha256 text NOT NULL,
                    patent_id text NOT NULL,
                    abstract text,
                    assignee_name text,
                    PRIMARY KEY (source_file_sha256, patent_id)
                )
            """)
        connection.commit()

    def write_raw(self, capture: RawCapture) -> str:
        connection = self._connect()
        with connection.cursor() as cursor:
            cursor.execute("""
                INSERT INTO diligence.raw_captures
                    (content_sha256, source_id, source_uri, params, retrieved_at, status_code, adapter_version, payload)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (content_sha256) DO NOTHING
            """, (capture.content_sha256, capture.request.source_id, capture.request.uri,
                   json.dumps(dict(capture.request.params)), capture.retrieved_at,
                   capture.status_code, capture.adapter_version, capture.payload))
        connection.commit()
        return f"postgresql://diligence/raw_captures/{capture.content_sha256}"

    def publish_entity_product(self, run_id: str, entities: list[dict[str, Any]], product: dict[str, Any], aliases: list[dict[str, Any]] | None = None, match_candidates: list[dict[str, Any]] | None = None) -> str:
        connection = self._connect()
        with connection.cursor() as cursor:
            for entity in entities:
                cursor.execute("""
                    INSERT INTO diligence.entities (entity_id, run_id, record)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (entity_id, run_id) DO UPDATE SET record = EXCLUDED.record
                """, (entity["entity_id"], run_id, json.dumps(entity, default=str)))
            for alias in aliases or []:
                cursor.execute("""
                    INSERT INTO diligence.entity_aliases (record_id, run_id, entity_id, record)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (record_id, run_id) DO UPDATE SET record = EXCLUDED.record
                """, (alias["record_id"], run_id, alias["entity_id"], json.dumps(alias, default=str)))
            for candidate in match_candidates or []:
                cursor.execute("""
                    INSERT INTO diligence.match_candidates (candidate_id, run_id, candidate_entity_id, record)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (candidate_id, run_id) DO UPDATE SET record = EXCLUDED.record
                """, (candidate["candidate_id"], run_id, candidate["candidate_entity_id"], json.dumps(candidate, default=str)))
            cursor.execute("""
                INSERT INTO diligence.product_manifests (materialization_id, product_id, pipeline_id, manifest)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (materialization_id) DO NOTHING
            """, (run_id, product["product_id"], product["pipeline_id"], json.dumps(product, default=str)))
        connection.commit()
        return f"postgresql://diligence/product_manifests/{run_id}"

    def close(self) -> None:
        if self._connection is not None:
            self._connection.close()
            self._connection = None

    def upsert_patent_index(self, records: list[dict[str, Any]], metadata: dict[str, Any]) -> int:
        connection = self._connect()
        with connection.cursor() as cursor:
            for record in records:
                search_text = " ".join(str(record.get(field) or "") for field in ("title", "abstract", "assignee_name"))
                cursor.execute("""
                    INSERT INTO diligence.patent_index (patent_id, source_file_sha256, record, search_text)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (patent_id) DO UPDATE SET
                        source_file_sha256 = EXCLUDED.source_file_sha256,
                        record = EXCLUDED.record,
                        search_text = EXCLUDED.search_text,
                        ingested_at = now()
                """, (record["patent_id"], metadata["source_file_sha256"], json.dumps(record, default=str), search_text))
            cursor.execute("""
                INSERT INTO diligence.patent_index_runs (source_file_sha256, source_path, metadata)
                VALUES (%s, %s, %s)
                ON CONFLICT (source_file_sha256) DO UPDATE SET metadata = EXCLUDED.metadata, ingested_at = now()
            """, (metadata["source_file_sha256"], metadata["source_path"], json.dumps(metadata, default=str)))
        connection.commit()
        return len(records)

    def stage_patent_enrichment(self, rows: list[dict[str, Any]], source_file_sha256: str) -> int:
        connection = self._connect()
        with connection.cursor() as cursor:
            for row in rows:
                cursor.execute("""
                    INSERT INTO diligence.patent_enrichment_staging (source_file_sha256, patent_id, abstract, assignee_name)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (source_file_sha256, patent_id) DO UPDATE SET
                        abstract = COALESCE(EXCLUDED.abstract, diligence.patent_enrichment_staging.abstract),
                        assignee_name = CASE
                            WHEN EXCLUDED.assignee_name IS NULL OR EXCLUDED.assignee_name = '' THEN diligence.patent_enrichment_staging.assignee_name
                            WHEN diligence.patent_enrichment_staging.assignee_name IS NULL OR diligence.patent_enrichment_staging.assignee_name = '' THEN EXCLUDED.assignee_name
                            WHEN position(EXCLUDED.assignee_name in diligence.patent_enrichment_staging.assignee_name) > 0 THEN diligence.patent_enrichment_staging.assignee_name
                            ELSE diligence.patent_enrichment_staging.assignee_name || '; ' || EXCLUDED.assignee_name
                        END
                """, (source_file_sha256, str(row["patent_id"]), row.get("abstract"), row.get("assignee_name")))
        connection.commit()
        return len(rows)

    def apply_patent_enrichment(self, source_file_sha256: str) -> int:
        connection = self._connect()
        with connection.cursor() as cursor:
            cursor.execute("""
                UPDATE diligence.patent_index AS p
                SET record = p.record || jsonb_strip_nulls(jsonb_build_object('abstract', s.abstract, 'assignee_name', s.assignee_name)),
                    search_text = concat_ws(' ', p.record->>'title', s.abstract, s.assignee_name),
                    ingested_at = now()
                FROM diligence.patent_enrichment_staging AS s
                WHERE s.source_file_sha256 = %s AND p.patent_id = s.patent_id
            """, (source_file_sha256,))
            updated = cursor.rowcount
        connection.commit()
        return updated

    def search_patent_index(self, query: str, limit: int = 25) -> list[dict[str, Any]]:
        connection = self._connect()
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT record
                FROM diligence.patent_index
                WHERE to_tsvector('simple', search_text) @@ plainto_tsquery('simple', %s)
                ORDER BY ts_rank(to_tsvector('simple', search_text), plainto_tsquery('simple', %s)) DESC, patent_id
                LIMIT %s
            """, (query, query, limit))
            return [row[0] for row in cursor.fetchall()]

    def publish_research_product(self, run_id: str, records: list[dict[str, Any]], product: dict[str, Any], observations: list[dict[str, Any]] | None = None, patent_records: list[dict[str, Any]] | None = None, assignments: list[dict[str, Any]] | None = None, inventor_edges: list[dict[str, Any]] | None = None, institution_edges: list[dict[str, Any]] | None = None) -> str:
        connection = self._connect()
        with connection.cursor() as cursor:
            for record in records:
                cursor.execute("""
                    INSERT INTO diligence.research_works (work_id, run_id, record)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (work_id, run_id) DO UPDATE SET record = EXCLUDED.record
                """, (record["work_id"], run_id, json.dumps(record, default=str)))
            for observation in observations or []:
                cursor.execute("""
                    INSERT INTO diligence.technology_topic_observations (observation_id, run_id, record)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (observation_id, run_id) DO UPDATE SET record = EXCLUDED.record
                """, (observation["observation_id"], run_id, json.dumps(observation, default=str)))
            for patent in patent_records or []:
                cursor.execute("""
                    INSERT INTO diligence.patent_records (patent_id, run_id, record)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (patent_id, run_id) DO UPDATE SET record = EXCLUDED.record
                """, (patent["patent_id"], run_id, json.dumps(patent, default=str)))
            for table, rows in (("patent_assignments", assignments), ("inventor_edges", inventor_edges), ("institution_edges", institution_edges)):
                for row in rows or []:
                    cursor.execute(f"""
                        INSERT INTO diligence.{table} (record_id, run_id, record)
                        VALUES (%s, %s, %s)
                        ON CONFLICT (record_id, run_id) DO UPDATE SET record = EXCLUDED.record
                    """, (row["record_id"], run_id, json.dumps(row, default=str)))
            cursor.execute("""
                INSERT INTO diligence.product_manifests (materialization_id, product_id, pipeline_id, manifest)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (materialization_id) DO NOTHING
            """, (run_id, product["product_id"], product["pipeline_id"], json.dumps(product, default=str)))
        connection.commit()
        return f"postgresql://diligence/product_manifests/{run_id}"
