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

## Company financials (SEC XBRL)

`--facts-only` publishes a second product, `company_financials`, from the SEC
`companyfacts` API for each `--cik` or `--watchlist` entry. It is separate from
the entity run so the two can be refreshed independently, and its rows use the
same `entity:sec:<CIK>` IDs the entity graph produces.

```bash
PYTHONPATH=src python -m diligence_pipelines.cli run 01_entity_graph --facts-only \
  --facts-fixture tests/fixtures/sec_companyfacts.json
SEC_USER_AGENT='investment-diligence-pipelines/0.1 you@example.com' \
PYTHONPATH=src python -m diligence_pipelines.cli run 01_entity_graph --facts-only --cik 320193
# Read-only check; nothing is written:
PYTHONPATH=src python -m diligence_pipelines.cli validate-sec-facts --cik 320193
```

| Output | Grain | Notes |
| --- | --- | --- |
| `financial_facts` | One row per concept × period × filing | Bounded USD concept set (revenue aliases, R&D, capex, net income, operating income, total assets) from annual forms (10-K, 20-F, 40-F and amendments). `period_end` is when the figure applies; `filed_at` is when the SEC received it. Restated values stay as separate rows. Each row links to its filing index. |
| `financial_metrics` | One row per company × fiscal period end | Latest-filed annual values, `rd_intensity`, `capex_intensity`, `operating_margin`, `revenue_growth_yoy`, `as_of_filed`, `restated`, and `input_fact_ids` tracing every figure to its facts |

Formulas: intensity = expense / revenue; operating margin = operating income /
revenue; growth = revenue / prior-year revenue − 1, using the period ending
350–380 days earlier. Ratios are null when the denominator is missing or not
positive.

**Point-in-time use.** `financial_metrics` uses the latest-filed value for each
period, so a restated year carries a later `as_of_filed` and `restated: true`.
For backtests or as-of analysis, filter `financial_facts` on `filed_at` rather
than reading the metrics row; it retains the originally reported figure.

Publication is blocked if a fact lacks a filing date, a fact is dated before
its period ended, a metric references a missing fact, or SEC returns an error
instead of facts. The fixture is synthetic (CIK 999001).

Match suggestions remain `unreviewed`; name similarity is not ownership confirmation. The batch path supports watchlists larger than 100 entries, subject to source rate limits and policy review. Watchlist inputs are deduplicated and CIK/LEI syntax is validated before network collection; invalid identifiers fail before a source request is made.
