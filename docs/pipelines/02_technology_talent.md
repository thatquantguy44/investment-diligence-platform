# Pipeline 02 — Technology and talent signals

The pilot combines OpenAlex research metadata with a USPTO/PatentsView patent response to create `research_works`, `patent_records`, `patent_assignments`, `inventor_edges`, `institution_edges`, and deterministic `technology_topic_observations`. It is intentionally not an employment or technology-quality classifier.

Run a bounded search:

```bash
PYTHONPATH=src python -m diligence_pipelines.cli run 02_technology_talent \
  --query "solid state battery" \
  --max-results 10
```

Live patent collection requires `USPTO_API_KEY` in `config/variables.yaml` or the environment. The endpoint is configurable through `USPTO_API_URL`. The legacy PatentsView search service is currently unavailable during the USPTO Open Data Portal migration, so use the checked-in synthetic response for the working offline path:

```bash
PYTHONPATH=src python -m diligence_pipelines.cli run 02_technology_talent \
  --query "solid state battery" \
  --max-results 1 \
  --patent-fixture tests/fixtures/patents.json
```

## USPTO ODP bulk-data path

The replacement path is a local query over a downloaded USPTO Open Data Portal bulk file. The adapter accepts JSON, JSONL, CSV, and ZIP-wrapped versions of those formats:

```bash
PYTHONPATH=src python -m diligence_pipelines.cli run 02_technology_talent \
  --query "solid state battery" \
  --max-results 10 \
  --patent-bulk-file /path/to/uspTO-bulk-export.jsonl
```

This is the first build slice for the replacement architecture: source files remain the evidence boundary, matching is deterministic and local, and the existing patent records, assignments, inventor edges, and product manifest are published to the configured PostgreSQL `IDP` database. The next slice is a controlled ODP downloader/catalog step that resolves the selected dataset release and stores its checksum before ingestion. PatentsView now points users to ODP datasets rather than a drop-in search API. See the [USPTO PatentsView page](https://www.uspto.gov/ip-policy/economic-research/patentsview).

Each output record retains source identifiers, dates, authors/inventors, institutions/assignees, source-record IDs, and run IDs. Patent and research records remain source evidence; inventor and institution edges do not establish employment by a target company. Raw responses and the product manifest are published to the configured backend.

The USPTO migration currently provides PatentsView data downloads through the Open Data Portal rather than a documented drop-in replacement for this search request. Keep the endpoint configurable and update `USPTO_API_URL` locally when a supported replacement is available.

When PostgreSQL is configured, Pipeline 02 automatically searches `diligence.patent_index` and no longer depends on the retired PatentsView search hostname. You can query the index directly:

```bash
PYTHONPATH=src python -m diligence_pipelines.cli search-uspto-index \
  --query "coherent laser detection" \
  --limit 10
```

Use `--patent-source api` to explicitly select the legacy API path, or `--patent-fixture` / `--patent-bulk-file` for replay tests.
