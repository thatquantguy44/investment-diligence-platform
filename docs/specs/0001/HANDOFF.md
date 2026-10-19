# Spec 0001 Handoff

## Current state

Spec 0001 is implemented through a working pilot foundation:

- Pipeline 01 fetches SEC EDGAR company submissions, optionally enriches with
  GLEIF, preserves raw captures, validates records, and publishes locally or to
  PostgreSQL `IDP`.
- Pipeline 02 combines OpenAlex research metadata with a local USPTO ODP-backed
  patent index. It publishes research works, patents, assignments, inventor
  edges, institution edges, and topic observations. The canonical
  `diligence.patent_catalog` table is separate from run-scoped
  `diligence.patent_records` and can be backfilled with
  `materialize-patent-catalog` after the full index load completes.
- Pipeline 03 has a bounded UN Comtrade-compatible trade exposure slice with
  explicit coverage and missingness reporting. Its follow-on slice now includes
  a read-only `validate-comtrade` command and source-vintage/revision metadata
  capture. Live preview validation passes; country/sector approval and
  authenticated account coverage remain open.
- Pipeline 04 publishes a bounded USAspending awards product with modification
  history, recipient concentration, and unreviewed entity candidates. Live
  validation and sector approval remain open.
- Pipeline 05 publishes GDELT-discovered source documents and rule-based,
  evidence-checked event candidates. An LLM extractor and the review workflow
  remain open.
- The knowledge application can read the configured PostgreSQL graph or use
  embedded fixtures.

## Pipeline 02 handoff

Pipeline 02 is pilot-complete for its current boundary. Its primary sources
are OpenAlex and USPTO Open Data Portal bulk data. The local patent index is
queried from `diligence.patent_index` when PostgreSQL is configured; queries do
not call a remote patent search API by default.

The USPTO ODP workflow now includes:

1. Catalog search.
2. Deterministic artifact selection.
3. Streamed download with checksum sidecar.
4. Bounded and resumable bulk ingestion.
5. PostgreSQL full-text indexing and Pipeline 02 routing.
6. Scheduled release discovery with candidate snapshots.

The controlled refresh path now adds reviewed selection, checksum-aware
download preparation, release diff reporting, schema/coverage/freshness checks,
and catalog pagination with retry handling. It still does not automatically
ingest into PostgreSQL.

Release discovery intentionally does not select, download, or ingest a new
release. The source setup, API-key handling, scheduler wrapper, and commands
are documented in [`docs/sources/uspto_odp.md`](../../sources/uspto_odp.md).

## Next work

The next active work is to finish Pipeline 02 materialization and approve the
bounded Pipeline 03 scope:

- Confirm the full USPTO ingestion has completed.
- Run `PYTHONPATH=src python -m diligence_pipelines.cli materialize-patent-catalog`.
- Validate canonical counts and repeat-run deduplication.
- Select and review one Pipeline 03 reporter country and one HS sector basket
  in [`docs/pipelines/03_trade_exposure.md`](../../pipelines/03_trade_exposure.md).
- Confirm Comtrade primary/secondary key loading; never commit key values.

The following are deliberately lower priority and deferred:

- Assignee-to-entity matching against Pipeline 01.
- Inventor-to-entity matching against Pipeline 01.
- Reviewable match candidates with confidence, evidence, and analyst state.
- OpenAlex snapshot/backfill support and source-vintage comparison.
- Richer time-windowed patent/research counts and topic trends.

Do not infer current ownership, employment, technology quality, or company
affiliation from assignee, inventor, institution, or research records alone.

## Validation

Run the repository-level checks before handoff:

```bash
PYTHONPATH=src python -m pytest -q
PYTHONPATH=src python -m diligence_pipelines.cli validate-manifests
PYTHONPATH=src python -m diligence_pipelines.cli validate-docs
git diff --check
```

Use the configured PostgreSQL service only through the `IDP` database and keep
credentials in `config/variables.yaml` or the approved runtime secret store.
