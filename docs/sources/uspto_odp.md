# USPTO Open Data Portal / PatentsView

## Purpose

Pipeline 02 uses USPTO patent data as its primary technology signal. The current implementation has two paths:

1. **ODP bulk ingestion:** download official source artifacts, hash them, index patent metadata locally in PostgreSQL, and enrich with abstracts and disambiguated assignees.
2. **Legacy API/fixture path:** retain a configurable legacy API adapter and synthetic fixture path for compatibility and deterministic tests. The retired PatentsView search service should not be treated as the default production path.

## Access and credentials

The USPTO Open Data Portal catalog search requires an API key. Configure:

```yaml
USPTO_API_KEY: "your-key-here"
USPTO_ODP_CATALOG_URL: "https://api.uspto.gov/api/v1/datasets/products/search"
```

The local PostgreSQL patent index does not require a key after the bulk artifacts have already been downloaded and ingested. Keep the key in `config/variables.yaml` or the environment; never place it in a fixture, URL, commit, or frontend bundle.

## Recommended setup path

Search the ODP catalog:

```bash
PYTHONPATH=src python -m diligence_pipelines.cli search-uspto-odp \
  --query "granted patent disambiguated" \
  --output .data/uspto/catalog.json
```

Select one artifact:

```bash
PYTHONPATH=src python -m diligence_pipelines.cli select-uspto-odp \
  --catalog .data/uspto/catalog.json \
  --contains "g_patent.tsv" \
  --output .data/uspto/selection.json
```

For scheduled discovery, create an explicit review record before downloading:

```bash
PYTHONPATH=src python -m diligence_pipelines.cli review-uspto-odp \
  --discovery .data/uspto/odp_discovery.json \
  --candidate-index 0 \
  --reviewer "analyst@example.com" \
  --note "Approved current granted-patent product for the Pipeline 02 refresh" \
  --output .data/uspto/reviewed_selection.json
```

Prepare a reviewed release for download and validation. This command does not
ingest into PostgreSQL:

```bash
PYTHONPATH=src python -m diligence_pipelines.cli refresh-uspto-odp \
  --selection .data/uspto/reviewed_selection.json \
  --output .data/uspto/g_patent.tsv.zip \
  --previous-file .data/uspto/g_patent.previous.tsv.zip \
  --report-output .data/uspto/refresh_report.json \
  --quality-output .data/uspto/quality_report.json
```

The refresh report includes checksum change status, schema and completeness
checks, freshness information, and new/changed/removed patent ID examples.
Only an explicit `ingest-uspto-bulk` command changes the PostgreSQL patent
index.

Use the scheduler-friendly wrapper for the same reviewed-only operation:

```bash
./scripts/uspto_odp_refresh.sh \
  --selection .data/uspto/reviewed_selection.json \
  --output .data/uspto/g_patent.tsv.zip \
  --report-output .data/uspto/refresh_report.json \
  --max-age-days 45
```

Every prepared, blocked, or failed refresh writes a durable report. Local runs
append to `.data/indexes/uspto_patents/odp_refresh_history.jsonl`; PostgreSQL
runs append to `diligence.uspto_odp_refreshes`. The wrapper exits nonzero for
blocked quality or download failures so an approved scheduler can route alerts.
It never invokes ingestion or promotion automatically.

The PostgreSQL model keeps two separate patent products:

- `diligence.patent_index` is the searchable USPTO bulk-release index.
- `diligence.patent_catalog` is the deduplicated canonical view keyed only by
  `patent_id`.
- `diligence.patent_records` remains run-scoped Pipeline 02 evidence keyed by
  `(patent_id, run_id)` so repeated analyses retain history.

After a full bulk ingestion finishes, backfill the canonical table without
re-reading the source archives:

```bash
PYTHONPATH=src python -m diligence_pipelines.cli materialize-patent-catalog
```

This command upserts from the current `patent_index`; it does not delete or
rewrite run-scoped `patent_records`.

Each PostgreSQL materialization records its UUID, source-file hashes, index and
catalog counts, parity-mismatch count, duration, and terminal status in
`diligence.patent_catalog_materializations`. A nonzero mismatch count returns a
nonzero CLI status and should be investigated before treating the catalog as
ready for downstream use.

Download the selected official artifact, then ingest a bounded pilot:

```bash
PYTHONPATH=src python -m diligence_pipelines.cli ingest-uspto-bulk \
  --patent-file .data/uspto/g_patent.tsv.zip \
  --abstract-file .data/uspto/g_patent_abstract.tsv.zip \
  --assignee-file .data/uspto/g_assignee_disambiguated.tsv.zip \
  --limit 100 \
  --batch-size 5000
```

Search the local index:

```bash
PYTHONPATH=src python -m diligence_pipelines.cli search-uspto-index \
  --query "solid state battery" \
  --limit 10
```

Pipeline 02 automatically uses `diligence.patent_index` when PostgreSQL is configured. Use `--patent-source index` to require that path, or `--patent-source api` only when a supported API endpoint is configured.

## Scheduled release discovery

The repository includes a scheduler-ready discovery wrapper:

```bash
./scripts/uspto_odp_discovery.sh
```

It polls the configured ODP catalog, records every matching downloadable
artifact, and does **not** select, download, or ingest a release. The default
query is `USPTO_ODP_PRODUCT_QUERY`; the latest snapshot is written to
`USPTO_ODP_DISCOVERY_OUTPUT`, with append-only history under
`.data/indexes/uspto_patents/odp_discovery_history.jsonl`. PostgreSQL also
stores each snapshot in `diligence.uspto_odp_discoveries`.

Run an offline smoke test:

```bash
DILIGENCE_STORAGE_BACKEND=local PYTHONPATH=src python -m diligence_pipelines.cli discover-uspto-odp \
  --catalog-fixture tests/fixtures/odp_catalog.json \
  --output .data/uspto/odp_discovery.json
```

Example crontab entry (every six hours; install on the host, not in Git):

```cron
0 */6 * * * cd /absolute/path/to/investment-diligence-platform && ./scripts/uspto_odp_discovery.sh >> .data/uspto/discovery.log 2>&1
```

On macOS, copy
`orchestration/com.investment-diligence.uspto-odp-discovery.plist.example` to
`~/Library/LaunchAgents/`, replace the two `/absolute/path/...` values, and
load it with `launchctl`. The template runs every `21600` seconds (six hours).

## Offline fixture path

```bash
PYTHONPATH=src python -m diligence_pipelines.cli run 02_technology_talent \
  --query "solid state battery" \
  --max-results 1 \
  --patent-fixture tests/fixtures/patents.json
```

`uspto_patents_fixture` and `patents.json` are synthetic test data. They are not USPTO evidence.

## Controls and limitations

- Preserve the selected release, source URL, local path, byte count, SHA-256, and adapter version.
- Treat dataset release and schema changes as review events.
- Assignee-to-entity matching is deferred; assignee records remain source evidence and unreviewed candidates.
- Patent inventorship does not establish employment by a target company.
- PatentsView data derived from USPTO records is research data and should not be presented as the official patent record without the appropriate qualification.

## Official references

- [USPTO PatentsView](https://www.uspto.gov/ip-policy/economic-research/patentsview)
- [USPTO research datasets](https://www.uspto.gov/ip-policy/economic-research/research-datasets)
- [USPTO ODP product search API](https://data.uspto.gov/apis/bulk-data/search)
