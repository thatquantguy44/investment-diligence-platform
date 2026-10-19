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

Pipeline `04_public_awards` (pilot) pulls a bounded USAspending contract or
grant search (date window plus NAICS/PSC/keyword filter), fetches modification
history for the top awards, and publishes `awards`, `award_events`,
`recipient_entities`, `technology_program_tags`, and `recipient_concentration`.
Obligation, outlay, and announced amounts stay separate. Recipient-to-entity
matches against a Pipeline 01 entities file are unreviewed candidates. See
[`docs/pipelines/04_public_awards.md`](pipelines/04_public_awards.md).

Pipeline `05_multilingual_events` (prototype) pulls one bounded GDELT DOC
article list, deduplicates URLs and syndicated copies, and extracts headline
event candidates with a rule-based extractor. Every candidate carries an exact
evidence span that a quality gate re-checks; nothing is promoted to a verified
event. It publishes `source_documents`, `event_candidates`,
`entity_event_edges`, and `event_signal_counts`. See
[`docs/pipelines/05_multilingual_events.md`](pipelines/05_multilingual_events.md).

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
- `diligence.patent_index`: searchable USPTO ODP bulk-release snapshot.
- `diligence.patent_catalog`: deduplicated canonical patent view keyed by
  `patent_id`.
- `diligence.patent_records`: run-scoped Pipeline 02 evidence keyed by
  `(patent_id, run_id)`.
- Pipeline 04: `diligence.awards`, `award_events`, `recipient_entities`,
  `technology_program_tags`, `recipient_concentration`, keyed by
  `(record_id, run_id)`.
- Pipeline 05: `diligence.source_documents`, `event_candidates`,
  `entity_event_edges`, `event_signal_counts`, keyed by `(record_id, run_id)`.

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

1. Confirm the full USPTO bulk ingestion has finished, then run
   `materialize-patent-catalog` against the completed `patent_index`.
2. Validate the deduplicated catalog count against the full index and confirm
   repeated Pipeline 02 runs do not increase canonical patent counts.
3. For Pipeline 03, approve one reporter country and one HS basket in the
   approval worksheet before broader live collection.
4. Load and validate Comtrade primary/secondary keys without exposing them;
   preview access currently works anonymously.
5. Add migrations before the PostgreSQL schema is used outside local development.
6. Keep Spec 0003 (WIFO/CNIPA) at placeholder status until a concrete dataset
   and diligence question are selected.
7. Run `validate-usaspending` and `validate-gdelt` against the live APIs from a
   machine with outbound access; the live connectors are only tested against
   mocked responses so far.
8. Approve one Pipeline 04 sector filter in the
   [approval worksheet](pipelines/04_public_awards.md#approval-worksheet-sector-filter)
   before broader live pulls.
9. Pipeline 05: add a local LLM extractor behind the `EventExtractor` protocol,
   build a small labeled evaluation set for the rules, and design the analyst
   review step that promotes candidates to verified events.

## Current validation result

The repository’s local test suite passes with 59 tests. Pipelines 04 and 05
publish from their synthetic fixtures to local storage and to a scratch
PostgreSQL 16 `IDP` database (all nine new tables populated). Their live
USAspending and GDELT paths were not run because the development sandbox had
no outbound access to those hosts. Manifest and
documentation validation pass. Pipeline 03 live preview validation returned
two USA lithium-ion battery records for 2024 with zero configured-HS-code
missingness; no data was written by the validation command. The full USPTO
release ingestion should be checked before running the catalog materialization
step above.
