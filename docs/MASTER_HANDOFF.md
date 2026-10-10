# Master Handoff — Investment Diligence Pipelines

## Purpose

This repository is the upstream data-pipeline boundary for investment diligence. It owns public-source acquisition, raw capture, normalization, entity resolution, provenance, quality checks, and versioned data products. Downstream QuantSmith-style research agents consume those products but are not dependencies of this repository.

## What is working now

Pipeline `01_entity_graph` has a lightweight real path:

1. Fetch one SEC EDGAR `submissions/CIK##########.json` document.
2. Store the response as an immutable, content-addressed raw capture.
3. Normalize the SEC CIK, company name, jurisdiction, tickers, and exchanges into the shared `Entity` contract.
4. Run schema, identifier, and source-reference quality gates.
5. Publish an entity record and product manifest to local storage or PostgreSQL.

The local fixture path remains the deterministic test path. SEC XBRL facts and ownership relationships are not implemented yet; those are follow-on enhancements to Pipeline 01.

## PostgreSQL target and configurability

The intended local backend is the PostgreSQL service used by `macro_medallion`:

| Setting | Default |
| --- | --- |
| Backend | `local` |
| Host | `localhost` |
| Port | `55432` |
| Database | `IDP` |
| User | `postgres` |
| Password | empty; inject at runtime |

Switch the backend with `DILIGENCE_STORAGE_BACKEND=postgres`. Override individual values with `DILIGENCE_POSTGRES_HOST`, `DILIGENCE_POSTGRES_PORT`, `DILIGENCE_POSTGRES_DB`, `DILIGENCE_POSTGRES_USER`, and `DILIGENCE_POSTGRES_PASSWORD`, or provide `DILIGENCE_POSTGRES_DSN`. The code does not depend on `macro_medallion` and does not assume that its database name or credentials are permanent.

The adapter creates a `diligence` schema in the configured database:

- `diligence.raw_captures`: append-only source payloads and retrieval metadata.
- `diligence.entities`: normalized entity records keyed by entity and run.
- `diligence.product_manifests`: product identity, contract version, materialization, quality, and lineage.

## Local variables and secrets

Store local runtime values in `config/variables.yaml`. This file is ignored by Git and is the intended place for the local PostgreSQL password and identifying SEC user agent. Create it from the tracked template:

```bash
cp config/variables_example.yaml config/variables.yaml
```

Keep `config/variables_example.yaml` synchronized with the names and safe defaults required by the application. Never copy real passwords, API keys, or private connection strings into the example file. Environment variables override YAML values, and `DILIGENCE_VARIABLES_FILE` can select a different local variables file.

## How to test

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
python -m pytest -q
python -m diligence_pipelines.cli validate-manifests
python -m diligence_pipelines.cli run 01_entity_graph --input tests/fixtures/entity_graph.jsonl
```

To test the real SEC path:

```bash
SEC_USER_AGENT='investment-diligence-pipelines/0.1 you@example.com' \
python -m diligence_pipelines.cli run 01_entity_graph --cik 320193
```

To test PostgreSQL after installing the optional driver and confirming that the `IDP` database is running:

```bash
pip install -e '.[postgres]'
export DILIGENCE_STORAGE_BACKEND=postgres
export DILIGENCE_POSTGRES_HOST=localhost
export DILIGENCE_POSTGRES_PORT=55432
export DILIGENCE_POSTGRES_DB=IDP
export DILIGENCE_POSTGRES_USER=postgres
export DILIGENCE_POSTGRES_PASSWORD='your-password'
SEC_USER_AGENT='investment-diligence-pipelines/0.1 you@example.com' \
python -m diligence_pipelines.cli run 01_entity_graph --cik 320193
```

## Important operating boundaries

- SEC requests require an identifying `User-Agent` and bounded request volume.
- Raw source data is never committed to Git.
- A name-similarity match is only an unreviewed candidate; it is not ownership confirmation.
- Unknown timestamps stay null. `first_seen_at` is the local system retrieval time only when the pipeline has observed the record.
- Failed quality gates block publication.
- Production secrets belong in the approved runtime secret mechanism, not `.env`, manifests, or logs.

## Recommended next work

1. Add SEC retry/backoff tests, HTTP error fixtures, and a reviewed source-policy record.
2. Add SEC XBRL facts and ownership relationships if Pipeline 01 needs deeper graph coverage.
3. Add a normalized `source_records` table if downstream consumers need SQL joins over raw metadata.
4. Add a consumer adapter that reads product manifests by `product_id`, `contract_version`, and `materialization_id`.
5. Add migrations before the PostgreSQL schema is used outside local development.
6. Continue with Pipeline 02 using the handoff in [`HANDOFF_PIPELINE_02.md`](HANDOFF_PIPELINE_02.md).

## Current validation result

The repository’s local test suite passes with nine tests. Manifest validation passes. The three-company live SEC watchlist smoke test published successfully to PostgreSQL `IDP`.
