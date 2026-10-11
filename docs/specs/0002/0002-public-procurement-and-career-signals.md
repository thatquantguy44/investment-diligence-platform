# Spec 0002: Public Procurement and Career-Page Signals

**Status:** Draft for review  
**Version:** 0.1.0  
**Extends:** Spec 0001 — Investment Diligence Data Pipelines  
**Owner:** Quantitative diligence / data engineering  
**Last updated:** 2026-10-10

## 1. Purpose

Add two bounded public-data capabilities to the investment diligence pipeline platform:

1. Country-level procurement and grant notices for one selected country and one selected sector at a time.
2. Company career-page signals that track role counts and changes by function and location.

Both capabilities are discovery and diligence signals, not proof of revenue, production, funding quality, hiring plans, or investment merit. They must preserve original evidence and remain subject to the contracts, source policy, lineage, quality, and publication rules established by Spec 0001.

## 2. What is new relative to Spec 0001

Spec 0001 already includes a general Pipeline 04 for public awards, procurement, and grants, using USAspending as the reference connector and leaving a country-specific portal as an open question. Spec 0002 makes that country-specific pilot concrete without prescribing a country or portal before policy review.

Company career pages are not specified in Spec 0001. Spec 0002 adds them as a separate signal pipeline with explicit controls for stale, duplicate, speculative, and unauthorized collection.

## 3. Goals and non-goals

### Goals

- Make a fragmented, country-specific public procurement/grant record searchable while retaining the original-language notice and page.
- Start procurement collection with exactly one country, one sector, and a bounded source allowlist.
- Extract awardee, buyer, amount, date, project, and location with field-level evidence.
- Resolve awardees to the Pipeline 01 entity graph without forcing ambiguous matches.
- Track career-page role counts and changes by company, function, location, and observation date.
- Preserve the original job-page content or permitted extract for analyst review.
- Distinguish observed job-posting activity from claims about headcount, hiring intent, or company expansion.

### Non-goals

- Building a universal procurement portal crawler.
- Treating a notice as proof that a contract was performed, paid, or commercially successful.
- Treating job-posting counts as employee counts, confirmed hires, or certain expansion plans.
- Collecting pages that disallow access, require login, use a CAPTCHA, sit behind a paywall, or otherwise restrict collection.
- Circumventing robots directives, rate limits, technical controls, or site terms.

## 4. Proposed additions

### Pipeline 04 extension — Country procurement and grant notices

**Purpose:** Create a searchable, evidence-backed record of official procurement and grant notices for one selected country and sector.

**Pilot boundary:**

- `country_id`: one explicitly approved country.
- `sector_id`: one explicitly approved sector definition, including classification rules and synonyms.
- `source_allowlist`: official government, ministry, agency, procurement, grant, or public-finance portals only unless an approved source review expands the boundary.
- `collection_window`: explicit start and end dates or a documented backfill partition.

**Required extraction fields:**

- `notice_id` or source-native identifier.
- `notice_type` (tender, award, grant, solicitation, amendment, cancellation, or other source-native type).
- `buyer_or_issuing_body`.
- `awardee_or_recipient`.
- `amount`, `currency`, and amount type when available (estimated value, ceiling, award, obligation, grant amount, or other).
- `announcement_date`, `award_date`, `submission_deadline`, and `first_seen_at` when known.
- `project_title` and source-language description.
- `location` with country, region, city, or site fields when available.
- `sector_tags` and the rule or evidence used to assign them.
- `amendment_or_parent_notice_id` when available.

**Required evidence:**

- Original source URL and source page identifier.
- Original-language title and relevant excerpt or permitted page snapshot.
- Field-level locator such as HTML selector, PDF page, table row, or JSON path.
- Content hash and retrieval timestamp.
- Translation or summary output, if used, stored separately from the original text.

**Entity resolution:**

- Resolve awardees and buyers to Pipeline 01 entities through identifier, registry, or reviewed name-match evidence.
- Preserve unresolved awardees as source-native parties plus match candidates.
- Never convert a name similarity into a confirmed ownership or corporate-identity relationship without review.

**Important controls:**

- Separate notice, award, amendment, obligation, disbursement, and cancellation states.
- Deduplicate syndicated or mirrored notices without losing source references.
- Preserve revisions and amendments as new source observations; do not silently overwrite prior notices.
- Report portal coverage, inaccessible pages, missing amounts, missing dates, and sector-classification uncertainty.
- Treat a procurement or grant record as evidence of a public process or award only; it does not establish performance, revenue, product-market fit, or technology quality.

**MVP acceptance:**

- A user can select the approved country, sector, and date partition and retrieve a bounded set of notices.
- Every normalized notice can be traced to the original-language source page and source record.
- Awardee, buyer, amount, date, project, and location fields are either evidenced or explicitly null.
- Amendments and cancellations remain distinguishable from original notices.
- At least one reviewed entity match and one unresolved match case are represented in fixtures and tests.
- A coverage and missingness report accompanies the published product.

### Pipeline 06 — Company career-page signals

**Purpose:** Track public career-page postings as an early, weak signal of functional and geographic hiring activity.

**Initial source boundary:**

- Company-controlled career pages or explicitly authorized job-board pages.
- A configured allowlist of domains and career-page URL patterns.
- One observation partition per company and retrieval date.

**Required extraction fields:**

- `posting_id` or stable source-native job identifier when available.
- `company_entity_id` or unresolved company match candidate.
- `job_title`.
- `function` (for example engineering, manufacturing, sales, regulatory, finance, or other).
- `location`, including remote or multi-location status when stated.
- `employment_type` and `seniority` when available.
- `posted_at`, `updated_at`, `closing_at`, and `first_seen_at` when known.
- `source_url`, page title, and original-language description or permitted excerpt.
- `content_sha256`, retrieval timestamp, and parser version.
- `posting_status`: active, closed, stale, removed, or unknown.

**Derived outputs:**

- `career_postings`.
- `career_role_counts` by company, function, location, and observation date.
- `career_role_changes` with additions, removals, reactivations, and observed changes.
- `career_source_documents` and unresolved company match candidates.

**Important controls:**

- Counts are counts of observed postings, not employees, hires, open headcount, or guaranteed expansion.
- Flag duplicate postings across locations, departments, languages, and syndicated boards.
- Detect stale or speculative postings using source timestamps, repeated observations, page status, and documented heuristics; do not silently delete them.
- Keep an observation history so a posting disappearing from a page is not automatically treated as a filled role.
- Do not infer that a company has entered a location solely because one remote or recruiter-managed posting mentions it.
- Function and location classifications must retain the original title and description plus the classification method and confidence.
- LLM-assisted translation or classification must retain model, prompt, schema, and evidence metadata; deterministic counting and change calculations remain code-owned.

**Collection policy:**

- Collect only pages whose terms and access conditions permit the intended collection.
- Use an identified user agent, explicit rate limits, caching, and a stop condition for access denial or policy changes.
- No login, CAPTCHA, paywall, bot-evasion, identity rotation, or access-control bypass.
- If raw page retention is not permitted, retain permitted excerpts, hashes, retrieval metadata, and a source pointer.

**MVP acceptance:**

- A user can inspect postings and role counts by company, function, location, and observation date.
- Repeated observations produce reproducible additions, removals, and unchanged states.
- Duplicate, stale, and speculative cases are represented in fixtures and quality results.
- Each count can be traced to the contributing postings and original source locations.
- A career-page signal is labeled as a weak proxy in the product documentation and manifest.

## 5. Shared contract additions

Both pipelines use the Spec 0001 canonical envelope and add source-specific records. The following fields are mandatory for derived aggregates:

- `observation_date` or partition timestamp.
- `source_record_ids[]`.
- `transformation_version`.
- `classification_method` and `classification_confidence` when taxonomy is inferred.
- `limitations[]`.
- `quality_status`.

Procurement notices require `notice_id`, `buyer`, `awardee`, and source-native status fields. Career postings require `posting_id` where available, otherwise a documented deterministic fingerprint of stable fields. A fingerprint is not proof that two postings are the same job; duplicate decisions retain method and evidence.

## 6. Quality gates

### Procurement

- Source host is registered and allowlisted.
- Required source locator and content hash are present.
- Notice identifiers are unique within source and partition unless an amendment version explains the duplicate.
- Amounts have currency and amount type when present.
- Dates are not silently substituted for one another.
- Awardee and buyer match states are explicit.
- Coverage, missingness, and sector-classification results are published.

### Career pages

- Source host is registered and collection-policy approved.
- Posting identifiers or fingerprints are stable and explainable.
- Duplicate, stale, removed, and active states are distinguishable.
- Counts reconcile to the contributing posting records.
- Function and location classifications retain method, confidence, and original text.
- No aggregate is described as headcount, hires, revenue, or confirmed expansion.

## 7. Rollout

1. Select and approve one procurement country, sector definition, portal set, retention rule, and collection window.
2. Implement procurement fixtures and parser before connecting to the live portal.
3. Complete entity matching and amendment/cancellation handling for the procurement pilot.
4. Select a small, analyst-approved company set for career-page observation.
5. Review terms and access conditions for every career source before activation.
6. Implement posting snapshots, deduplication, stale detection, and role-count reconciliation.
7. Compare both products against analyst-reviewed cases before scheduling.

## 8. Open decisions

- Which country and sector should anchor the procurement pilot?
- Which official portal or portals are in scope, and what retention/reuse terms apply?
- Which procurement taxonomy maps to the sector basket?
- Which initial company set and career-page providers are approved?
- What is the minimum evidence standard for an awardee-to-entity match?
- How long should career-page snapshots and permitted excerpts be retained?
- Which posting-change heuristics should produce a warning rather than a hard failure?

## 9. Traceability to Spec 0001

| Spec 0002 area | Spec 0001 foundation |
| --- | --- |
| Official-source allowlist and collection controls | REQ-012, NFR-006, source policy |
| Raw page and notice preservation | REQ-003, REQ-006, raw storage zone |
| Awardee/company entity resolution | REQ-008, Pipeline 01 entity graph |
| Original language and evidence spans | REQ-006, EvidenceRef |
| Point-in-time job and notice observations | REQ-005, `first_seen_at` semantics |
| Versioned products and downstream access | REQ-014, product manifest |
| Quality and coverage reporting | REQ-010–011, validation strategy |
