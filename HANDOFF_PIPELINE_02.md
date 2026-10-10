# Handoff to Pipeline 02 — Technology and Talent Signals

## Starting point

Pipeline 01 is complete for the current pilot boundary. It provides the patterns Pipeline 02 should reuse:

- Direct CLI execution with a pipeline ID and bounded input.
- `RawCapture` with content hash, retrieval time, source URI, status, and adapter version.
- Pydantic canonical records with explicit point-in-time fields.
- PostgreSQL backend selected through `config/variables.yaml` or environment variables.
- PostgreSQL database `IDP`, schema `diligence`.
- Append-only raw captures in `diligence.raw_captures`.
- Per-run curated records and product manifests in `diligence.entities` and `diligence.product_manifests`.
- Quality checks that block publication.

Do not import QuantSmith code into this repository.

## Pipeline 02 scope from Spec 0001

Purpose: compare company technology claims with patent, inventor, research, and institutional evidence.

Initial sources:

- USPTO research datasets / Open Data Portal.
- OpenAlex API or public snapshot.

Required outputs:

- `patent_records`
- `patent_assignments`
- `inventor_edges`
- `research_works`
- `institution_edges`
- `technology_topic_observations`

## Recommended implementation sequence

1. Add `pipelines/02_technology_talent/manifest.yaml` with source domains, rate limits, terms review, outputs, and quality checks.
2. Add source adapters under `src/diligence_pipelines/sources/` only for behavior needed by this pipeline; keep source-native payloads intact.
3. Define source-specific Pydantic records plus a small canonical envelope. Preserve application, filing, publication, assignment, grant, and first-seen dates separately.
4. Link patent assignees and inventors to Pipeline 01 entities through explicit match candidates and review states. Do not infer employment from coauthorship alone.
5. Add deterministic formulas for time-windowed counts and topic observations. Patent counts are signals, not quality judgments.
6. Add synthetic fixtures and HTTP replay tests before live calls.
7. Publish a product manifest with formula versions, source hashes, coverage, missingness, and limitations.

## Acceptance criteria

- A user can query a company or topic and inspect the patents or works contributing to each output.
- Every aggregate has a reproducible formula and explicit time window.
- Patent filing, publication, grant, assignment, and first-seen timestamps are not conflated.
- Low-confidence entity links remain unresolved.
- Curated publication is blocked when schema, source-reference, completeness, or duplicate checks fail.

## First files to inspect

- `src/diligence_pipelines/contracts/models.py`
- `src/diligence_pipelines/sources/sec.py`
- `src/diligence_pipelines/storage/postgres.py`
- `src/diligence_pipelines/cli.py`
- `pipelines/01_entity_graph/manifest.yaml`
- `tests/test_cli.py`

## Validation before handoff

```bash
python3 -m pytest -q
PYTHONPATH=src python3 -m diligence_pipelines.cli validate-manifests
```

Use the existing local PostgreSQL service only through the configured `IDP` database. Do not add credentials to tracked files.
