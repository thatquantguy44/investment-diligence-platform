# Investment Diligence Pipelines

Modular, source-backed data pipelines for investment diligence. The repository owns source capture, normalization, entity resolution, provenance, quality gates, and versioned data-product contracts. Downstream research systems consume published products through those contracts; they are not imported here.

## Status

The foundation and Pipeline 01 pilot are in place. Pipeline 01 can fetch a bounded SEC EDGAR watchlist, optionally enrich entries with GLEIF LEI records, preserve raw responses, normalize entities and aliases, run quality checks, and publish versioned product manifests. Local fixture replay remains available for deterministic tests.

## Quick start

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'

python -m diligence_pipelines.cli validate-manifests
python -m diligence_pipelines.cli run 01_entity_graph --input tests/fixtures/entity_graph.jsonl
pytest
```

### Run the real pipeline

SEC requires an identifying `User-Agent`. Use an email address you control:

```bash
SEC_USER_AGENT='investment-diligence-pipelines/0.1 you@example.com' \
python -m diligence_pipelines.cli run 01_entity_graph --cik 320193
```

The example uses Apple’s SEC CIK. Replace `320193` with another public-company CIK. The run is bounded to one SEC submissions document; it does not crawl filings or bypass access controls.

For a bounded batch run, copy and edit [`config/watchlist_example.yaml`](config/watchlist_example.yaml):

```bash
SEC_USER_AGENT='investment-diligence-pipelines/0.1 you@example.com' \
python -m diligence_pipelines.cli run 01_entity_graph --watchlist config/watchlist_example.yaml
```

Each watchlist entry requires a CIK and may include a 20-character LEI. An LEI triggers a GLEIF capture and an exact-identifier alias; name similarity alone remains unreviewed.

Runtime data is written under `.data/` by default and is excluded from Git. Set `DILIGENCE_DATA_ROOT` to use another local root.

### Local variables

Save local credentials and runtime settings in `config/variables.yaml`. It is ignored by Git. Start from the tracked template:

```bash
cp config/variables_example.yaml config/variables.yaml
# edit config/variables.yaml locally
```

`config/variables_example.yaml` is the shareable template to update when new variables are introduced. Environment variables override values from `config/variables.yaml`; use `DILIGENCE_VARIABLES_FILE` to point to another YAML file.

### PostgreSQL backend

All pipeline storage is selected through configuration. The intended local PostgreSQL convention is the existing `macro_medallion` instance on port `55432`, with all investment-diligence products in database `IDP`:

```bash
pip install -e '.[postgres]'
export DILIGENCE_STORAGE_BACKEND=postgres
export DILIGENCE_POSTGRES_HOST=localhost
export DILIGENCE_POSTGRES_PORT=55432
export DILIGENCE_POSTGRES_DB=IDP
export DILIGENCE_POSTGRES_USER=postgres
export DILIGENCE_POSTGRES_PASSWORD='your-password'

python -m diligence_pipelines.cli run 01_entity_graph --cik 320193
```

These are defaults, not hard-coded requirements. Use `DILIGENCE_POSTGRES_DSN` for a complete connection string, or override the host, port, database, user, and password independently. The PostgreSQL adapter creates a `diligence` schema with `raw_captures`, `entities`, and `product_manifests` tables. Local filesystem storage remains the default for offline development and tests.

## Design rules

- Raw captures are append-only and addressed by content hash.
- Unknown timestamps remain null; they are never silently replaced by another timestamp.
- Entity matches are suggestions until explicitly reviewed.
- Curated publication is blocked when required quality checks fail.
- Secrets and production data are runtime concerns, never repository contents.

See [docs/architecture.md](docs/architecture.md), [docs/data-contracts.md](docs/data-contracts.md), and [docs/pipelines/01_entity_graph.md](docs/pipelines/01_entity_graph.md).

Source setup, credential handling, endpoints, rate limits, fixture paths, and operating controls are documented in [docs/sources/](docs/sources/README.md).

For a complete implementation handoff, see [docs/MASTER_HANDOFF.md](docs/MASTER_HANDOFF.md).

For cross-spec sequencing and deferred work, see [docs/MASTER_ROADMAP.md](docs/MASTER_ROADMAP.md). Each specification also has its own roadmap: [Spec 0001](docs/specs/0001/ROADMAP.md), [Spec 0002](docs/specs/0002/ROADMAP.md), and the provisional [Spec 0003](docs/specs/0003/ROADMAP.md).

Machine-generated changes follow the [agent workflow](docs/CONTRIBUTING_AGENT_WORKFLOW.md). Before handoff or commit, validate code, manifests, documentation links, and whitespace:

```bash
PYTHONPATH=src python -m pytest -q
PYTHONPATH=src python -m diligence_pipelines.cli validate-manifests
PYTHONPATH=src python -m diligence_pipelines.cli validate-docs
git diff --check
```

Pipeline 02 now has a pilot-complete OpenAlex + USPTO/PatentsView slice. See [docs/pipelines/02_technology_talent.md](docs/pipelines/02_technology_talent.md).

Pipeline 04 adds a bounded USAspending public-awards pilot and Pipeline 05 adds a GDELT-backed event-candidate prototype. See [docs/pipelines/04_public_awards.md](docs/pipelines/04_public_awards.md) and [docs/pipelines/05_multilingual_events.md](docs/pipelines/05_multilingual_events.md).
