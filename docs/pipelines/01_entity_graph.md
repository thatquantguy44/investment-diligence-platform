# Pipeline 01 — Company and ownership graph

This pilot canonicalizes a bounded local input file or SEC EDGAR watchlist into `entities` and publishes a product manifest. Optional LEIs trigger GLEIF captures and exact-LEI aliases.

See the source runbooks for [SEC EDGAR](../sources/sec_edgar.md) and [GLEIF](../sources/gleif.md).

## Direct run

```bash
PYTHONPATH=src python -m diligence_pipelines.cli run 01_entity_graph --input tests/fixtures/entity_graph.jsonl
# Real public SEC source; Apple is CIK 320193.
SEC_USER_AGENT='investment-diligence-pipelines/0.1 you@example.com' \
PYTHONPATH=src python -m diligence_pipelines.cli run 01_entity_graph --cik 320193
# Batch mode.
PYTHONPATH=src python -m diligence_pipelines.cli run 01_entity_graph --watchlist config/watchlist_example.yaml
```

The run writes an immutable raw capture, a curated entity, quality results, and a manifest containing the materialization ID and lineage. Re-running the same input creates a new materialization and does not overwrite the prior raw capture. Use `DILIGENCE_STORAGE_BACKEND=postgres` to publish to PostgreSQL.

SEC and optional GLEIF requests use bounded retries for transient transport failures and HTTP 429/5xx responses. Invalid CIK/LEI identifiers are rejected before any network request.

Match suggestions remain `unreviewed`; name similarity is not ownership confirmation. The batch path supports watchlists larger than 100 entries, subject to source rate limits and policy review. Watchlist inputs are deduplicated and CIK/LEI syntax is validated before network collection; invalid identifiers fail before a source request is made.
