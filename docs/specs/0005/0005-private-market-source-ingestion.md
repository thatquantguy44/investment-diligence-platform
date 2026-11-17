# Spec 0005: Private-market source ingestion

**Status:** Draft for review  
**Version:** 0.1.0  
**Extends:** Spec 0001 and Pipeline 01 entity graph  
**Owner:** Investment diligence / data engineering  
**Last updated:** 2026-11-17  
**Branch:** `feature/ingest-crunchbase-fundcomb-openvc`

## 1. Problem and decision

Scope Crunchbase, FundComb, and OpenVC as possible sources of private-company, financing, and investor evidence for the investment diligence platform. The decision is which source-backed records can be collected, retained, and published under each provider's actual access rights, and whether they improve investor and company coverage beyond the current SEC/GLEIF pilot.

The research question is whether these providers add useful, verifiable private-market coverage. The engineering requirement is to capture permitted observations with provenance, quality checks, and reviewed entity matches. A provider profile or estimated size is an observation, not proof of legal identity, a completed financing, or investment merit.

**Working assumption:** the first use case is a bounded watchlist of companies and investors. OpenVC is being considered for investor discovery; its separate startup deal-flow and LP products are outside this pilot until the intended use is confirmed.

## 2. Scope and source assessment

| Source | Proposed pilot | Verified access path | Gate before live collection |
| --- | --- | --- | --- |
| Crunchbase | Company/investor profiles and financing rounds for a bounded watchlist | Licensed v4 REST API; organization lookup and search documented. Package and field access depend on the order form. | Provisioned key, package/field inventory, order-form rights, retention and downstream-use approval. |
| FundComb | Published investor profiles and transaction comps | Managed-beta Data API for entitled Data-plan workspaces. `GET /api/v1/investors` requires `read:investors`; `GET /api/v1/comps` requires `read:comps`. | Workspace entitlement, scoped key, response `rightsPolicy` review, permitted retention/use, provider rate limit. |
| OpenVC | Investor profiles, preferences, stage and sector fit if licensed | Public investor database is visible. The published investor-database page advertises CSV import and **CRM** export; this is not evidence of a provider-database export or API entitlement. | Provider-approved API/export or written permission for the intended automated collection, field and retention rights, access/rate controls. No live adapter until resolved. |

### Crunchbase boundary

The pilot requests only licensed organization identifiers, names, URLs, descriptions, locations, categories, investor status, and financing round/investment facts needed by a stated diligence question. Exact fields and collections must be selected from the provisioned package's reference and a sample response. Store the stable Crunchbase UUID separately from the permalink. Preserve round IDs, amounts, currency, announced dates, investor participants, source-native status, and nulls only where the licensed package actually supplies them. Do not imply a company's total funding equals capital currently available.

Use the v4 lookup endpoint for known organizations and bounded Search API queries for discovery. Search uses `after_id` keyset pagination; hold the query, fields, sort, and limit fixed for a traversal. The documented Enterprise ceiling is 200 requests/minute/key and 3 concurrent requests/key; the runtime cap must be configurable and may be lower. Bulk exports are a distinct, contract-dependent path and are not part of the initial API pilot.

### FundComb boundary

Pilot `read:investors` first; add `read:comps` only if the comps use case and rights are approved. The official API documents `limit` 1–100, numeric `nextCursor`, and optional text `q` for investors. Comps have an optional exact `sector` filter. Page until `nextCursor` is null or a configured cap is reached; incomplete traversal must be marked incomplete. The response's rights/provenance metadata, including source, confidence, attribution, and `rightsPolicy`, must stay with each observation. FundComb's estimated FUM and transaction comps are attributed estimates/observations, not independently verified fund assets or executed deal economics.

A free public website does not establish permission for automated collection. The documented Data API entitlement is the proposed access path. The site documents no rate ceiling on the developer page inspected, so the production cap requires provider or contract confirmation.

### OpenVC boundary

First determine whether OpenVC offers an authorized API, licensed export, or written integration agreement for investor profiles. Verify whether any export covers provider-supplied profiles, as the visible page describes exporting a user's CRM. If access is approved, pilot only firm-level public or licensed fields such as profile URL, firm name, investor type, geography, preferred stages/sectors, check-size range, and last verified/updated date when supplied. Contact details, founder interactions, outreach state, and LP/deal-flow data require separate rights and privacy review. Without an approved access path, limit work to schema design and synthetic fixtures; do not infer an API from website requests or crawl authenticated pages.

## 3. Functional requirements

| ID | Priority | Requirement and verification |
| --- | --- | --- |
| REQ-01 | Must | Record a source-specific access decision before live runs: account entitlement, permitted endpoints/fields, allowed host, terms version/review date, retention period, redistribution/derived-product rights, rate cap, and owner. A missing or expired decision blocks live collection. |
| REQ-02 | Must | Each enabled adapter accepts a bounded watchlist, time window where supported, page/record budget, and dry-run option. A run report shows attempted, completed, skipped, and failed partitions. |
| REQ-03 | Must | Capture every successful response immutably with source ID, sanitized URI/parameters, retrieval time, status, adapter version, content hash, raw location, and run ID. Never put credentials in URLs, logs, manifests, or raw metadata. |
| REQ-04 | Must | Normalize source-native company, investor, funding-round, investment, and comp records only when fields are present and licensed. Preserve native IDs, field semantics, original currency/units, source dates, observed time, and explicit nulls. A source-native payload remains available within approved retention. |
| REQ-05 | Must | Produce Pipeline 01 entity/match candidates with exact external IDs where available. Name/domain similarity yields an unreviewed candidate; it never silently merges entities or asserts an investment relationship. |
| REQ-06 | Must | Store each financing or investor-company relationship as a distinct source assertion with evidence and status. A Crunchbase round, FundComb comp, or OpenVC preference must not be treated as interchangeable proof. |
| REQ-07 | Must | Handle pagination, retries, rate limits, 429/5xx, credential failures, and partial runs. Retry only transient failures with bounded backoff; stop on access denial or policy change. Never publish a partial traversal as complete. |
| REQ-08 | Must | Preserve corrections, removals, and changed values as later observations. Record provider publication/update dates only when supplied; retrieval time cannot substitute for them. |
| REQ-09 | Must | Quality gates check required IDs, referential links, duplicate native IDs, monetary units, date ordering, pagination completeness, source rights, and provenance. Failed gates block curated publication and leave a report. |
| REQ-10 | Should | Publish source-specific coverage and freshness reports for the bounded watchlist, including missing fields, conflicting claims, stale records, and unresolved matches. |
| REQ-11 | Should | Provide a controlled backfill and incremental refresh path after the pilot establishes source behavior and provider permissions. |

## 4. Non-functional requirements and constraints

| ID | Priority | Requirement and verification |
| --- | --- | --- |
| NFR-01 | Must | Enforce HTTPS and narrow host/path allowlists for requests and redirects. Reject unexpected origins before sending credentials. |
| NFR-02 | Must | Credentials come from runtime secret injection or ignored local variables, never checked-in files. Use Crunchbase `X-cb-user-key` and FundComb Bearer headers where authorized. |
| NFR-03 | Must | Bound response bytes, pages, records, run duration, and concurrent requests. Source policy caps are configuration, with a safe lower default until the provider's limit is known. |
| NFR-04 | Must | Make replay idempotent at the source-native ID + observation/version level and retain append-only raw capture hashes. Re-running an unchanged page may create a new observation but must not create duplicate curated facts. |
| NFR-05 | Must | Apply provider-specific retention, deletion, attribution, and downstream-use rules to raw captures and published products. If the contract forbids the platform's append-only retention, design an approved metadata/hash-only or expiring capture mode before live collection. |
| NFR-06 | Must | Keep personally identifiable contact data out of the pilot. Any later person-level scope needs a separate lawful-basis and access review. |
| NFR-07 | Should | Report per-source requests, rows, failures, estimated quota consumption, and cost. Set a run budget before each live pilot; provider price and quota are currently unknown. |

The initial pilot target is a small operator-selected watchlist, not a full-provider mirror. Refresh cadence and latency target remain open until entitlement, quotas, and the investment decision's timing are known. No provider-specific SLA is assumed.

## 5. Data products and evidence

Proposed grains, subject to licensed fields:

- `private_market_source_profiles`: one source-native organization or investor profile per source observation; includes provider ID, profile URL, observed time, and field-level lineage.
- `private_market_financing_assertions`: one provider-native funding round or investment assertion per observation; amount, currency, date, participants, and source status remain source-specific.
- `investor_fit_observations`: one provider-stated stage, sector, geography, or check-size preference per investor profile observation. This is a stated preference, not evidence of willingness to invest.
- `private_market_match_candidates`: proposed links to canonical Pipeline 01 entities, with evidence, score/method, and review status.
- `private_market_coverage`: run-level completion, missingness, freshness, and rights status.

Version any shared contract change. Keep source-only fields in source payloads until another pipeline demonstrates a common need. A published manifest must enumerate source, run, schema version, completeness, rights class, and upstream capture hashes. If provider terms prohibit storing a raw payload or exposing a field to downstream consumers, the product must omit it or remain unpublished.

## 6. Delivery sequence and dependencies

1. **Access and license inventory:** obtain the Crunchbase order form/package and sample responses; FundComb Data-plan/API entitlement and sample `rightsPolicy`; OpenVC written integration/export terms. Record source-policy reviews and retention decisions.
2. **Contract and fixture review:** use permitted redacted examples or synthetic fixtures to settle field mappings, native IDs, date meanings, and quality thresholds.
3. **Crunchbase watchlist pilot:** bounded lookup/search, raw capture, normalization, match candidates, quality report, and manifest.
4. **FundComb investor pilot:** bounded investor pages with rights metadata and coverage report; comps follow only after separate approval.
5. **OpenVC pilot:** only after the access gate; otherwise leave it as a documented candidate source.
6. **Operational readiness:** review run budgets, schedules, monitoring, deletion handling, and downstream consumer rights before enabling recurring runs.

The source owner/contract holder owns access and commercial terms; data engineering owns adapter behavior and provenance; a diligence analyst owns match reviews and whether the resulting fields answer a research question; a privacy/compliance reviewer owns person data and redistribution decisions. These are proposed roles, not assumed sign-offs.

## 7. Out of scope

Full-platform scraping, login automation, CAPTCHA or bot-control workarounds, bulk mirroring without a licensed bulk product, investor outreach, CRM writeback, LP/contact ingestion, person-level enrichment, automatic investment recommendations, and automatic cross-source claim reconciliation. A paid UI subscription alone does not authorize an API pipeline.

## 8. Constraints & Risks

| ID | Risk | Control |
| --- | --- | --- |
| RISK-01 | Crunchbase license may limit fields, retention, combination, derived products, or redistribution. | Confirm the actual order form and data terms before capture/publication; block disallowed products. |
| RISK-02 | FundComb beta entitlement or row-level `rightsPolicy` may differ across records. | Check entitlement and rights per response/row; exclude restricted rows from publication. |
| RISK-03 | OpenVC may not offer a licensed automated data path. | Keep source inactive until provider authorization and documented interface exist. |
| RISK-04 | The three sources can disagree or revise historical facts. | Retain separate source assertions and observation times; show conflicts to analysts. |
| RISK-05 | Fundraising, FUM, check sizes, and preferences can be estimated or stale. | Preserve source labels and update timestamps; avoid stronger claims than the evidence supports. |
| RISK-06 | Existing immutable raw capture design may conflict with a provider retention/deletion obligation. | Resolve retention design and deletion process before live runs. |

## 9. Public source references reviewed 2026-11-17

- [Crunchbase API essentials](https://data.crunchbase.com/docs/api-essentials), [API packages](https://data.crunchbase.com/docs/api-packages-overview), [Search API](https://data.crunchbase.com/docs/search-api-basics), [pagination](https://data.crunchbase.com/docs/paginate-search-results), [bulk exports](https://data.crunchbase.com/docs/legacy-exports), and [data access terms](https://data.crunchbase.com/docs/data-access-terms). Public docs describe capabilities; the applicable order form determines rights.
- [FundComb Data API](https://www.fundcomb.com/developers), [FAQ](https://www.fundcomb.com/faq), and [methodology](https://www.fundcomb.com/methodology).
- [OpenVC investor database](https://www.openvc.app/investor-database) and [pricing](https://www.openvc.app/pricing). No public provider data API or bulk license was established from these pages.

## Open Questions

1. **Product owner:** Which diligence decisions take priority: company financing verification, investor mapping, comparable deals, or investor fit? What pilot watchlist and geography should measure value?
2. **Crunchbase contract owner:** Which package, fields, quotas, data-use rights, retention, deletion, and derived-product restrictions apply? Is a bulk export licensed?
3. **FundComb workspace owner:** Is Data API beta enabled, which scopes can be issued, what is the allowed request rate, and how should `rightsPolicy` govern storage and publication?
4. **OpenVC provider/account owner:** Is there an authorized investor-database API or licensed export, and does it permit automated storage and internal downstream use? Does the desired scope include startup deal flow instead of investor profiles?
5. **Data/product owners:** What freshness target, refresh cadence, coverage threshold, run budget, and destination audience are required? Who reviews conflicting funding facts and match candidates?
6. **Compliance/data owner:** What retention and deletion process satisfies each agreement while preserving auditable lineage?

## Acceptance Criteria

| ID | Evidence required |
| --- | --- |
| AC-01 | Each activated source has a documented entitlement, allowed fields/endpoints, terms review, rights/retention decision, rate cap, and owner in the source registry or linked policy record. |
| AC-02 | A bounded fixture replay for each proposed source produces versioned source-native records, raw capture lineage, explicit nulls, and a complete run report; unapproved OpenVC uses synthetic fixtures only. |
| AC-03 | Approved live pilot for each enabled source finishes within its configured page/request budget, reports completeness and coverage, and has zero leaked credentials in logs/manifests. |
| AC-04 | Tests show 429/5xx retry behavior, 401/403 stop behavior, redirect host rejection, duplicate-page protection, interrupted pagination, changed source facts, and restricted-rights exclusion. |
| AC-05 | No curated record publishes without its source ID, source-native identifier, observation time, evidence reference, rights class, and passing quality result. |
| AC-06 | At least one exact-ID match, one ambiguous match, one conflicting cross-source assertion, and one later revision are reviewed in fixtures or a permitted redacted sample. |
| AC-07 | The diligence analyst validates that the chosen pilot records answer the stated research question, with measured watchlist coverage, missingness, and freshness against thresholds agreed before the run. |
