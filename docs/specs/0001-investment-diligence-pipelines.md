# Spec 0001: Investment Diligence Data Pipelines

**Status:** Draft for review  
**Version:** 0.1.0  
**Repository name:** `investment-diligence-pipelines`  
**Owner:** Quantitative diligence / data engineering  
**Last updated:** 2026-10-10

## 1. Purpose

Create a modular upstream repository for collecting, validating, linking, and publishing data products that support investment diligence on early-stage companies and their surrounding markets, with an initial focus on China and Southeast Asia.

The repository must make pipelines easy to add without creating a new one-off ETL pattern for each source. It will provide shared contracts for source records, entities, relationships, events, evidence, lineage, and point-in-time observations. Each pipeline will publish reusable, documented, versioned data products for separate downstream research systems.

**QuantSmith is the natural downstream connection.** This repository owns source acquisition, normalization, entity resolution, provenance, and data-product publication. QuantSmith owns downstream research agents and workflows that consume the published products. The boundary is a versioned data contract; the pipeline code must not depend on QuantSmith's agent framework.

This repository handles public and otherwise explicitly authorized data only. It does not store or process classified, controlled, licensed-restricted, or client-confidential data unless a later approved deployment design explicitly authorizes that environment and data class. No source datasets or credentials belong in Git.

## 2. Goals and non-goals

### Goals

- Make each pipeline independently runnable, testable, observable, and backfillable.
- Standardize source capture, provenance, timestamps, schemas, and quality checks.
- Preserve original source records separately from normalized and derived data.
- Support APIs, bulk downloads, and policy-compliant public-web collection through a common source adapter interface.
- Use local LLMs behind a replaceable interface for multilingual extraction and entity-match suggestions, while keeping deterministic code responsible for calculations and publication.
- Start with the agreed build order: entity graph; technology and talent signals; trade exposure; public awards; multilingual events.
- Keep the codebase usable on a developer workstation and deployable inside a client-approved environment.

### Non-goals for the first release

- Training a foundation model or building a general-purpose autonomous agent.
- Making investment decisions or automatically issuing recommendations.
- Treating country-level trade data, news volume, patent counts, or satellite detections as direct proof of a company’s revenue, production, or technology quality.
- Building a universal crawler for every country or source portal.
- Storing raw data in the Git repository.

## 3. Assumptions and constraints

1. The initial target is a small number of analysts and a handful of scheduled or manually triggered pipelines; scale will be measured before designing for thousands of concurrent jobs.
2. Python is the primary implementation language.
3. Initial development uses local files and local analytical storage. Production storage and orchestration must be selected or approved for the target environment.
4. Dagster is the proposed orchestration default because its [asset model](https://docs.dagster.io/) supports lineage, partitioning, and independent materialization. Pipeline functions must still run from a CLI without Dagster so the code is portable and easy to test. Dagster's [partition documentation](https://docs.dagster.io/guides/build/partitions-and-backfills) describes partitioned assets and backfills.
5. Local LLM inference is available in the target environment, but a specific model, serving runtime, GPU platform, and approval boundary are not yet specified.
6. Source terms, licenses, API limits, and applicable collection rules must be reviewed for each source before activation. “Free to access” does not imply unrestricted reuse.

## 4. Requirements

### Functional requirements

- **REQ-001 — Pipeline registry:** Every pipeline must have a machine-readable manifest describing its purpose, owner, sources, schedule, outputs, sensitivity class, collection method, and operational limits.
- **REQ-002 — Shared source interface:** API, bulk-file, and permitted web-page collectors must implement a common interface for fetch metadata, raw payload capture, retry behavior, and error reporting.
- **REQ-003 — Immutable source capture:** Every successful source fetch must record retrieval time, source URL or API endpoint, request parameters with secrets removed, response status, content hash, source update/publication time when available, and adapter version.
- **REQ-004 — Canonical records:** Pipelines must publish records using shared schemas for entities, aliases, relationships, observations, events, documents, evidence, and quality results.
- **REQ-005 — Point-in-time semantics:** Records must distinguish event time, publication time, first-seen time, and effective time when those values are known. Unknown timestamps remain null; they must not be inferred silently.
- **REQ-006 — Provenance:** Every derived record must reference one or more source-record IDs and transformation versions. LLM-extracted claims must retain supporting text spans or source locations.
- **REQ-007 — Reprocessing:** A pipeline must support rerunning a named time or source partition without overwriting prior raw captures. Derived outputs must be reproducible from pinned source snapshots and code/model versions.
- **REQ-008 — Entity resolution:** Match suggestions must include method, score, candidate evidence, and review state. Low-confidence matches must remain unresolved rather than being forced into an entity.
- **REQ-009 — Local model boundary:** LLM use must go through a replaceable local inference interface. Prompts, model IDs, model revisions, extraction schema versions, and outputs must be logged without exposing secrets or restricted source content.
- **REQ-010 — Quality gates:** Each pipeline must define schema, freshness, completeness, duplication, and domain-specific checks before publishing curated assets.
- **REQ-011 — Observability:** Runs must emit structured logs, source and row counts, latency, retries, quality results, data freshness, and materialization identifiers.
- **REQ-012 — Collection policy:** Web collection must use an explicit source allowlist, documented terms review, identified user agent where applicable, rate limits, caching, and a stop condition for access denial or policy changes. No login, paywall, CAPTCHA, or access-control bypass.
- **REQ-013 — No data in Git:** Git may contain code, schemas, synthetic fixtures, and source manifests. Raw source data, API keys, model weights, and production outputs are excluded.
- **REQ-014 — Downstream data products:** Every curated output intended for external consumption must have a stable `product_id`, contract version, availability/freshness metadata, partition manifest, and documented access method. QuantSmith consumers must be able to identify the exact product and version used for a run.

### Non-functional requirements

- **NFR-001 — Reproducibility:** The same pinned input snapshots, code version, configuration, and model revision should produce equivalent normalized outputs, excluding documented nondeterminism.
- **NFR-002 — Auditability:** A reviewer must be able to trace a published feature or claim back to its raw source and transformation history.
- **NFR-003 — Safe failure:** A failed or partial run must not publish a success-marked curated asset.
- **NFR-004 — Portability:** Core transformation and validation logic must not depend on a cloud-vendor-specific SDK.
- **NFR-005 — Cost awareness:** Fetch volume, storage growth, model calls, and compute time must be measurable per pipeline.
- **NFR-006 — Security:** Credentials must be injected at runtime from an approved secret mechanism; logs and manifests must redact them.
- **NFR-007 — Consumer compatibility:** Breaking changes to published schemas require a new major contract version and a migration note; additive optional fields use a compatible minor version.

## 5. Proposed repository layout

```text
investment-diligence-pipelines/
├── README.md
├── pyproject.toml
├── uv.lock
├── .env.example                 # names only; no usable secrets
├── .gitignore
├── specs/
│   └── 0001-investment-diligence-pipelines.md
├── docs/
│   ├── architecture.md
│   ├── data-contracts.md
│   ├── source-policy.md
│   ├── operations.md
│   └── pipeline-catalog.md
├── config/
│   ├── defaults.yaml
│   ├── source-registry.yaml
│   └── environments/
│       ├── local.example.yaml
│       └── approved-runtime.example.yaml
├── schemas/
│   ├── entity.schema.json
│   ├── observation.schema.json
│   ├── event.schema.json
│   └── evidence.schema.json
├── src/diligence_pipelines/
│   ├── contracts/               # Pydantic models and schema exports
│   ├── sources/                  # shared API, bulk, and web adapters
│   ├── storage/                  # local and approved object-store interfaces
│   ├── lineage/                  # run, source, transform, and model metadata
│   ├── entities/                 # normalization, aliases, match candidates
│   ├── llm/                      # local inference protocol and structured output
│   ├── quality/                  # common validation helpers
│   ├── settings.py
│   └── cli.py
├── pipelines/
│   ├── 01_entity_graph/
│   │   ├── manifest.yaml
│   │   ├── README.md
│   │   ├── assets.py
│   │   ├── config.example.yaml
│   │   ├── src/
│   │   └── tests/
│   ├── 02_technology_talent/
│   ├── 03_trade_exposure/
│   ├── 04_public_awards/
│   ├── 05_multilingual_events/
│   └── 90_facility_activity/     # later phase; not required for MVP
├── orchestration/
│   └── dagster_defs.py
├── tests/
│   ├── contracts/
│   ├── integration/
│   └── fixtures/                 # synthetic or explicitly redistributable only
└── scripts/
    ├── check_source_policy.py
    └── validate_manifests.py
```

Pipeline directories own source-specific extraction and domain logic. Shared code belongs in `src/diligence_pipelines/` only after at least two pipelines need the same behavior. This keeps the core small and prevents speculative abstractions.

## 6. Architecture and data flow

```text
Source API / bulk file / permitted public page
        ↓
Source adapter → immutable raw capture + fetch manifest
        ↓
Parse and normalize → canonical records + source references
        ↓
Entity linking / local LLM-assisted extraction (where useful)
        ↓
Quality gates → curated data assets → derived indicators
        ↓ versioned data-product contract
QuantSmith and other approved downstream research consumers
```

### Upstream/downstream boundary

- **This repository owns:** source registry, collection policy, raw capture metadata, canonical schemas, entity graph, curated data products, quality status, and product versioning.
- **QuantSmith owns:** downstream agents, research orchestration, cross-product synthesis, user-facing explanations, and agent/tool integrations.
- **Contract:** publish versioned schemas plus a product manifest containing `product_id`, `contract_version`, `materialization_id`, partition keys, `as_of`/freshness metadata, lineage references, and storage-neutral location/access details.
- **Consumption:** downstream code reads through a consumer adapter. A local Parquet reader is the first implementation; approved object-store or API readers can be added without changing pipeline business logic. QuantSmith may expose the consumed products to agents through its own tool or MCP layer.
- **Dependency direction:** downstream consumers may depend on this repository's published contract. Pipeline code and pipeline CI must not import QuantSmith packages or call QuantSmith agents.
- **Security:** downstream access is granted by the deployment environment and product classification. Agents receive only products they are authorized to use; credentials are not passed through prompts or tool arguments.

### Storage zones

- **Raw:** Append-only source payloads with a content hash and retrieval metadata. Keep source-native format where practical.
- **Normalized:** Typed, source-preserving records represented as Parquet or JSONL. Retain original text and original names alongside normalized values.
- **Curated:** Entity graph, technology signals, trade exposure, public award records, and event records with lineage attached.
- **Features:** Explicitly derived indicators, each with formula, inputs, availability timestamp, limitations, and version.

The repository stores no production datasets. Local development can use a configurable filesystem root and DuckDB for inspection. Production storage is an adapter behind a storage interface; select the implementation only after the approved runtime is known.

## 7. Shared data contracts

All canonical records include `record_id`, `schema_version`, `pipeline_id`, `source_id`, `run_id`, and `created_at`. Identifiers should be deterministic when practical, using stable source keys or a documented hash of stable fields. Every published product also includes a product manifest and contract version so QuantSmith can preserve the exact upstream inputs used by a research run.

### Required common record types

- **SourceRecord:** `source_record_id`, `source_id`, `source_uri`, `retrieved_at`, `published_at`, `source_updated_at`, `content_sha256`, `http_status`, `request_fingerprint`, `adapter_version`, `raw_object_uri`.
- **Entity:** `entity_id`, `entity_type`, `canonical_name`, `jurisdiction`, `identifiers[]`, `first_seen_at`, `entity_status`, `evidence_refs[]`.
- **EntityAlias:** `entity_id`, `alias`, `language`, `script`, `transliteration_method`, `source_record_id`, `match_method`, `match_score`, `review_status`.
- **Relationship:** `subject_entity_id`, `predicate`, `object_entity_id`, `valid_from`, `valid_to`, `first_seen_at`, `confidence`, `evidence_refs[]`.
- **Observation:** `entity_id`, `metric`, `value`, `unit`, `period_start`, `period_end`, `published_at`, `first_seen_at`, `source_record_id`, `method`, `limitations`.
- **Event:** `event_id`, `event_type`, `event_time`, `published_at`, `first_seen_at`, `entities[]`, `claim_text`, `language`, `evidence_refs[]`, `extraction_method`, `confidence`, `review_status`.
- **EvidenceRef:** `source_record_id`, `locator` (URL, page, table, JSON path, or text span), `quote_or_excerpt` when permitted, `content_sha256`.
- **QualityResult:** `check_id`, `status`, `measured_at`, `partition_key`, `observed_value`, `threshold`, `details`.

For point-in-time research, `first_seen_at` is the system-availability timestamp. It must not be replaced by `event_time` or `published_at`. Corrected or revised observations create a new version or observation; historical records are not silently rewritten.

### Pipeline interface

Every pipeline implements these logical stages, callable directly from Python and the CLI:

```python
discover(config, window) -> list[SourceRequest]
fetch(request, context) -> RawCapture
normalize(capture, context) -> list[CanonicalRecord]
enrich(records, context) -> list[CanonicalRecord]  # optional; LLM/entity linking
validate(records, context) -> QualityReport
publish(records, report, context) -> Materialization
```

`context` carries the run ID, source registry, storage handles, clock, logger, model client (if enabled), and execution mode. Production publishing is blocked when required checks fail.

## 8. Initial pipeline specifications and build order

### Pipeline 01 — Company and ownership graph

**Purpose:** Establish canonical company and related-entity identities for later pipelines.

**Initial sources:** [SEC EDGAR submissions and XBRL company facts](https://www.sec.gov/search-filings/edgar-application-programming-interfaces); [GLEIF LEI records and ownership data](https://www.gleif.org/en/lei-data/gleif-api). EDGAR covers public filing histories and structured financial facts; GLEIF includes legal-entity reference data and fuzzy search, but LEI coverage will be incomplete for private startups. GLEIF states that its LEI data is freely accessible and provided under [CC0](https://www.gleif.org/en/lei-data/access-and-use-lei-data).

**Outputs:** `entities`, `entity_aliases`, `entity_relationships`, `filing_observations`, `unresolved_match_candidates`.

**Important controls:** Preserve CIK and LEI as source identifiers; never equate name similarity with confirmed ownership. Include manual review state for match candidates.

**MVP acceptance:** Ingest a configurable watchlist of at least 100 entities; preserve all source identifiers and fetch dates; create no automatic confirmed match below the configured threshold; re-run a partition without changing prior raw captures.

### Pipeline 02 — Technology and talent signals

**Purpose:** Compare company technology claims with patent, inventor, research, and institutional evidence.

**Initial sources:** [USPTO research datasets/Open Data Portal](https://www.uspto.gov/ip-policy/economic-research/research-datasets) and the [OpenAlex API](https://help.openalex.org/api/) or [public snapshot](https://help.openalex.org/access/snapshot/). OpenAlex offers free API access and a snapshot refreshed quarterly; it is a research-metadata source, not a complete talent database.

**Outputs:** `patent_records`, `patent_assignments`, `inventor_edges`, `research_works`, `institution_edges`, `technology_topic_observations`.

**Important controls:** Patent counts are not quality; patent publication and assignment dates differ; distinguish filing date, publication date, grant date, and first-seen date. Do not infer employment from coauthorship alone.

**MVP acceptance:** A user can query a company/topic and inspect the patents or works contributing to each output; each aggregate has a reproducible formula and time window.

### Pipeline 03 — Trade and supply-chain exposure

**Purpose:** Measure country/product trade flows and concentration relevant to a target sector or investment thesis.

**Initial source:** [UN Comtrade API](https://uncomtrade.org/docs/un-comtrade-api/) with recorded subscription tier, request quota, reporting country, partner, flow, commodity code, and frequency. Free access has limits and license terms; the pipeline must honor both. See the [subscription](https://uncomtrade.org/docs/subscriptions/), [API key](https://uncomtrade.org/docs/api-subscription-keys/), and [data-use policy](https://uncomtrade.org/docs/policy-on-comtrade-data-use/).

**Outputs:** `trade_flows`, `product_country_exposure`, `partner_concentration`, `mirror_trade_discrepancies`.

**Important controls:** Trade flows are country/product aggregates and do not establish that a named company imported or exported a product. Handle revisions, reporter coverage, units, re-exports, and HS-code vintages explicitly.

**MVP acceptance:** Reproducible monthly or annual pulls for a configured sector basket; explicit coverage and missingness report; formulas for concentration and mirror discrepancies documented and unit-tested.

### Pipeline 04 — Public awards, procurement, and grants

**Purpose:** Detect public funding and procurement evidence around target technologies, competitors, and comparable firms.

**Initial source:** [USAspending API](https://api.usaspending.gov/docs/) as a working implementation of the connector pattern. Add one selected country portal only after a source policy review and country-specific schema assessment. USAspending exposes public federal spending through an API.

**Outputs:** `awards`, `solicitations`, `recipient_entities`, `award_events`, `technology_program_tags`.

**Important controls:** Separate announcement, obligation, and disbursement amounts and dates; deduplicate amendments; entity-match recipients with review states. A contract award does not prove commercial product-market fit.

**MVP acceptance:** Download and normalize a bounded set of award records; retain award identifiers and amendment history; analyst can inspect the original record for every normalized award.

### Pipeline 05 — Multilingual company and policy event stream

**Purpose:** Discover potentially material events in local-language and English public sources, then create evidence-backed structured event records.

**Initial source:** [GDELT DOC API](https://blog.gdeltproject.org/gdelt-doc-2-0-api-debuts/) for discovery, followed by a configurable allowlist of primary-source company, regulator, exchange, and government pages. GDELT should not be treated as a complete news archive or authority for the truth of a claim.

**Outputs:** `source_documents`, `event_candidates`, `verified_events`, `entity_event_edges`.

**Local LLM usage:** Translate or summarize source text; extract candidate event fields into a strict schema; return quoted evidence spans and uncertainty. A model output is an extracted claim, not a verified fact. Keep the source language and original excerpt.

**Important controls:** Deduplicate syndicated stories; retain source and publication time; separate event time from report time; require review or independent confirmation for material events.

**MVP acceptance:** Each extracted event has a source locator and excerpt; unsupported facts fail validation; model name, revision, prompt version, and extraction schema are recorded; low-confidence events stay candidates.

### Later pipeline — Facility activity

[NASA FIRMS](https://firms.modaps.eosdis.nasa.gov/api/) can support a narrowly scoped facility watch for thermal anomalies or fires. It must not be used as a generalized production estimate; any signal needs geospatial validation and corroboration.

## 9. Pipeline manifest

Each `manifest.yaml` must validate against a shared schema and include:

```yaml
pipeline_id: "01_entity_graph"
title: "Company and ownership graph"
status: "prototype"  # prototype | pilot | active | paused | retired
owner: "team-or-role"
purpose: "Canonicalize companies and related entities"
sources:
  - source_id: "sec_edgar"
    method: "api"
    terms_reviewed: true
    max_requests_per_minute: 8
    allowed_domains: ["data.sec.gov", "www.sec.gov"]
outputs: ["entities", "entity_aliases", "entity_relationships"]
schedule: "manual"
partition_by: ["source_id", "retrieval_date"]
sensitivity: "public"
model_use: "none"
quality_checks: ["schema_valid", "identifier_unique", "source_ref_present"]
```

The example is illustrative. Source-specific limits and access conditions must be confirmed before activation.

## 10. Proposed technology choices

- **Language/runtime:** Python; `uv` for environment and lockfile management.
- **Contracts:** Pydantic models with generated JSON Schema and explicit schema versions.
- **Tabular persistence:** Parquet for raw/normalized/curated files; DuckDB for local inspection and development.
- **Orchestration:** Dagster OSS as a proposed default; preserve direct CLI execution for every stage. Confirm operational and security fit before deployment.
- **LLM access:** A local `ModelClient` protocol exposing structured generation, model metadata, and health status. Implement an adapter only for the approved serving runtime.
- **Testing:** pytest; schema contract tests, deterministic unit tests, adapter tests with synthetic HTTP fixtures, and small integration tests against approved public endpoints.
- **Configuration:** YAML manifests with environment-specific values and runtime secret injection. Commit examples, never secrets.
- **Storage backend:** Local filesystem first; production object-store implementation remains an adapter decision.

Do not add Kubernetes, a graph database, a feature store, or a separate vector database in the MVP unless a measured requirement justifies it. The entity graph can begin as relational edge tables; local LLM retrieval can use the client-approved search/index service later.

## 11. Validation strategy

| Area | Verification | Release gate |
|---|---|---|
| Contracts | Validate each output against versioned schemas | No invalid records published |
| Source capture | Hash and metadata checks; replay from fixtures | Same fixture yields same normalized records |
| Time alignment | Tests for event/publication/first-seen distinctions and revisions | No missing timestamp silently filled with another timestamp |
| Entity resolution | Gold set with confirmed, ambiguous, and negative pairs | No forced merge for ambiguous or negative cases |
| LLM extraction | Evidence-span coverage, field-level precision/recall, unsupported-claim checks | Thresholds set on an analyst-reviewed evaluation set before pilot |
| Data quality | Freshness, completeness, duplicate, range, and domain checks | Critical checks pass before curated publication |
| Access policy | Manifest policy validation; source collector refuses unapproved hosts | No unregistered source can be fetched in production mode |
| Reproducibility | Re-run pinned raw partition and compare canonical outputs | Differences explained and versioned |

Evaluation sets must contain licensed/redistributable examples or synthetic fixtures. Store labels and annotations with provenance and permitted access controls.

## 12. Observability and operations

Every run records pipeline/version, run ID, partition keys, source IDs, start/end times, row counts, raw hashes, retry counts, API status, model/version when used, quality outcomes, output locations, and materialization status.

Alerts should cover failed runs, stale sources, unexpected volume shifts, schema drift, repeated rate-limit/access-denied responses, rising unresolved entity rates, and LLM extraction-quality regressions. A run with partial source coverage is marked partial and cannot appear as fully current.

## 13. Failure modes and rollback

- **Source changes or disappears:** Keep prior raw captures and published assets; mark source stale; pause the affected pipeline; add a versioned adapter after fixture-based validation.
- **Rate limit or access denial:** Honor `Retry-After` where supplied, use bounded exponential backoff, then stop. Repeated denial opens a source-policy review; do not rotate identities or evade controls.
- **Schema drift:** Quarantine the new payload shape, emit an alert, and block curated publication until the parser and tests are updated.
- **Bad entity merge:** Preserve source records and match decision history; revert the merge by publishing a superseding relationship state; recompute downstream assets from the prior entity mapping version.
- **LLM regression or model replacement:** Pin model revision and prompt/schema version; canary against the evaluation set; roll back the model adapter/configuration while preserving prior outputs and evidence.
- **Corrupt derived asset:** Mark the materialization invalid, restore the last good output, and rematerialize from immutable raw captures and a pinned code version.

## 14. Rollout

1. **Foundation:** Define contracts, source registry, local storage, CLI, manifest validation, CI checks, and the downstream product manifest.
2. **Pipeline 01:** Implement the entity graph and manual review workflow.
3. **Pipelines 02–03:** Add patent/research and trade exposure using the shared contracts.
4. **Pipeline 04:** Add USAspending as the procurement/grants reference implementation; select one Asia portal only after policy and schema review.
5. **Pipeline 05:** Add multilingual event discovery and local LLM extraction behind evidence and quality gates.
6. **Pilot:** Run against a bounded, analyst-approved watchlist; compare outputs against manually reviewed cases; establish freshness and quality thresholds before scheduling broadly.
7. **QuantSmith integration:** Validate a consumer adapter against the versioned product contract in a development environment; record the product and contract version in each downstream agent run; keep agent orchestration in QuantSmith.

Pipelines move through `prototype → pilot → active`. Promotion requires passing the pipeline-specific acceptance criteria, source-policy review, an owner, alert routing, and a documented recovery procedure.

## 15. Trade-offs

- **Dagster vs. custom scheduling:** Dagster is the default because asset lineage and partitioned materialization fit this repository. Custom scheduling is simpler initially, but it makes dependency visibility and backfills harder as pipelines accumulate. Keep the pipeline functions scheduler-independent to preserve portability.
- **One shared canonical model vs. source-specific schemas:** Use a small canonical envelope plus source-specific payloads. A universal ontology would overfit the initial sources; source-only outputs would make cross-pipeline analysis brittle.
- **Raw retention vs. storage minimization:** Retain raw captures only when source terms and policy allow it. Otherwise retain permitted extracts, hashes, retrieval metadata, and pointers. This reduces storage and licensing risk while preserving some auditability.
- **Automatic entity matching vs. review-first:** Use automated candidate generation, but require explicit confidence and review state for consequential links. This sacrifices some immediate coverage to reduce false ownership and identity claims.
- **Local LLM vs. deterministic extraction:** Use local LLMs for language-heavy extraction and translation, but keep numerical transformations and final feature calculations deterministic. The model can propose structured records; it cannot silently certify their truth.
- **Code repository vs. data lake:** Keep code, schemas, and fixtures in Git; store datasets and materializations in a separately configured data store. This supports repo review without embedding licenses, sensitive information, or large data artifacts.
- **Shared code vs. downstream integration:** Publish schemas and data-product manifests as the stable interface. Avoid importing QuantSmith runtime code into the pipeline repository; this keeps ingestion deployable and testable when the agent framework or execution environment changes.

## 16. Risks and open questions

- Which approved runtime, storage backend, and network boundary will host the pipelines and local models?
- Which source licenses allow raw payload retention, derived-data redistribution, and analyst access?
- Which China and Southeast Asia jurisdictions/sectors should the first country-specific procurement or regulatory collector cover?
- What watchlist and human review process will seed and correct the entity graph?
- Which local LLM serving interface and model revisions are approved, and what is the required throughput/latency?
- What retention periods and access controls apply to collected public material in the eventual client environment?
- What minimum evidence standard is required before an event moves from candidate to verified?
- Is Dagster OSS deployable in the client environment, or should the first release use a scheduler already approved there?

## 17. Traceability matrix

| Requirement | Design elements |
|---|---|
| REQ-001 | Pipeline manifest; `config/source-registry.yaml`; pipeline catalog |
| REQ-002–003 | Shared source adapters; `SourceRecord`; immutable raw zone |
| REQ-004–006 | Canonical contracts; evidence references; lineage metadata; point-in-time fields |
| REQ-007 | Partitioned assets; immutable captures; CLI replay; pinned versions |
| REQ-008 | Entity match candidates, scores, evidence, and review state |
| REQ-009 | Local `ModelClient`; model/prompt/schema version metadata |
| REQ-010–011 | Quality checks; structured run logs; freshness and volume alerts |
| REQ-012–013; NFR-006 | Source allowlist; collection policy; secret injection; Git exclusions |
| REQ-014; NFR-007 | Versioned data-product manifest; consumer adapter; compatibility policy; QuantSmith downstream integration |
| NFR-001–005 | Lockfile; deterministic tests; lineage; failure gates; cost and volume metrics |

