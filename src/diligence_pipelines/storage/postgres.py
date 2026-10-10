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

    def publish_research_product(self, run_id: str, records: list[dict[str, Any]], product: dict[str, Any], observations: list[dict[str, Any]] | None = None) -> str:
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
            cursor.execute("""
                INSERT INTO diligence.product_manifests (materialization_id, product_id, pipeline_id, manifest)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (materialization_id) DO NOTHING
            """, (run_id, product["product_id"], product["pipeline_id"], json.dumps(product, default=str)))
        connection.commit()
        return f"postgresql://diligence/product_manifests/{run_id}"
