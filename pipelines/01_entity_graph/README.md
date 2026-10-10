# Pipeline 01 — Company and ownership graph

This prototype canonicalizes either a bounded local input file or one real SEC EDGAR company-submissions response into `entities` and publishes a product manifest. GLEIF remains a planned adapter.

## Direct run

```bash
PYTHONPATH=src python -m diligence_pipelines.cli run 01_entity_graph --input tests/fixtures/entity_graph.jsonl
# Real public SEC source; Apple is CIK 320193.
SEC_USER_AGENT='investment-diligence-pipelines/0.1 you@example.com' \
PYTHONPATH=src python -m diligence_pipelines.cli run 01_entity_graph --cik 320193
```

The run writes an immutable raw capture, a curated entity, quality results, and a manifest containing the materialization ID and lineage. Re-running the same input creates a new materialization and does not overwrite the prior raw capture. Use `DILIGENCE_STORAGE_BACKEND=postgres` to publish to PostgreSQL.

Match suggestions remain `unreviewed`; name similarity is not ownership confirmation.
