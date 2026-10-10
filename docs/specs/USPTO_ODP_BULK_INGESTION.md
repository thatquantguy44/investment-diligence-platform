# USPTO ODP bulk patent ingestion

## Objective

Replace the retired PatentsView query dependency with a reproducible local patent index sourced from USPTO Open Data Portal (ODP) bulk data. Preserve the current Pipeline 02 outputs and PostgreSQL/`IDP` publication contract.

## Scope

### In scope

- Configurable ODP dataset/file selection and release metadata.
- Download or registration of the original bulk artifact with checksum and retrieval timestamp.
- JSON, JSONL, CSV, and ZIP-wrapped input support.
- Deterministic title/abstract matching for bounded Pipeline 02 queries.
- Existing `patent_records`, `patent_assignments`, `inventor_edges`, and product-manifest outputs.
- Local replay from a downloaded artifact without calling a remote search API.

### Out of scope for this slice

- Reconstructing a full PatentsView search service.
- Treating patent inventorship as employment or ownership evidence.
- Loading the entire historical USPTO corpus into PostgreSQL in one command.
- Automatic entity resolution without reviewable match candidates.

## Build phases

1. **Implemented:** local bulk-file adapter and deterministic query path.
2. **Implemented:** streamed artifact downloader with ODP API-key header support and a SHA-256 JSON sidecar.
3. **Implemented:** ODP product-catalog search command using an ODP API key.
4. **Implemented:** deterministic catalog selection command that requires exactly one matching release/file.
5. **Implemented:** schema-validated bulk indexing with PostgreSQL `diligence.patent_index` and a local replay index.
6. **Next:** incremental refresh, checksum-based deduplication, schema-drift checks, and coverage metrics.

## Test command

```bash
PYTHONPATH=src python -m diligence_pipelines.cli run 02_technology_talent \
  --query "solid state battery" \
  --max-results 1 \
  --patent-bulk-file tests/fixtures/patents_bulk.jsonl
```

This keeps OpenAlex live but uses a local patent bulk fixture. Once an ODP artifact is downloaded, replace the fixture path with that artifact path. The current official USPTO guidance directs users to ODP-hosted PatentsView datasets rather than a drop-in legacy search endpoint.

Download a selected artifact once its official ODP URL is known:

```bash
PYTHONPATH=src python -m diligence_pipelines.cli download-uspto-bulk \
  --url "https://data.uspto.gov/..." \
  --output .data/uspto/patents.jsonl
```

The command writes `.data/uspto/patents.jsonl.json` with the source URL, retrieval time, byte count, HTTP status, and SHA-256 checksum.

Index the downloaded artifact into the configured backend:

```bash
PYTHONPATH=src python -m diligence_pipelines.cli index-uspto-bulk \
  --file .data/uspto/patents.jsonl
```

PostgreSQL creates `diligence.patent_index` with a simple-language GIN search index and `diligence.patent_index_runs` for source checksums and ingestion metadata.

Search the ODP product catalog:

```bash
PYTHONPATH=src python -m diligence_pipelines.cli search-uspto-odp \
  --query "PatentsView granted patent disambiguated" \
  --output .data/uspto/catalog.json
```

Select one release/file before downloading it:

```bash
PYTHONPATH=src python -m diligence_pipelines.cli select-uspto-odp \
  --catalog .data/uspto/catalog.json \
  --contains "PatentsView granted patent disambiguated 2025-Q4" \
  --output .data/uspto/selection.json
```
