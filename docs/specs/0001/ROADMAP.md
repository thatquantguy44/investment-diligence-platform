# Spec 0001 Roadmap

This roadmap covers the original investment diligence pipeline specification.
The cross-spec sequencing lives in the repository [MASTER_ROADMAP.md](../../MASTER_ROADMAP.md).

## Current status

- Pipeline 01 is complete for the current SEC/GLEIF pilot boundary.
- Pipeline 02 is complete for the current OpenAlex plus USPTO ODP-backed patent
  index pilot; operational hardening is the next active work.
- Pipeline 03 has a bounded trade-exposure pilot.

## Pipeline 02 — active hardening

1. Scheduled ODP release discovery — implemented.
2. Reviewed artifact selection and checksum-aware download preparation — implemented.
3. Schema-drift, freshness, coverage, and missingness checks — implemented for release preparation.
4. Source pagination, rate-limit, and HTTP replay tests — implemented for catalog discovery.
5. Release diff reporting and controlled PostgreSQL refresh preparation — implemented; ingestion remains explicit.
6. Full-release ingestion at production scale and alerting — next.
7. Deduplicated canonical `patent_catalog` materialization — implemented; backfill is explicit after a completed index load.
8. OpenAlex 429 handling with `Retry-After` support and bounded longer backoff — implemented and tested.

## Pipeline 02 — lower-priority backlog

These items are intentionally deferred until the local index and release
refresh path are stable:

- Assignee-to-entity matching against Pipeline 01.
- Inventor-to-entity matching against Pipeline 01.
- Reviewable candidate records with confidence, evidence, and analyst state.
- OpenAlex snapshot/backfill support and source-vintage comparison.
- Richer time-windowed counts, topic trends, and historical comparisons.
- Additional patent fields only when their source coverage and semantics are
  documented.

The system must continue to treat assignee, inventor, institution, and research
records as evidence records—not proof of ownership, employment, or technology
quality.

## Pipeline 01 follow-ons

- SEC XBRL facts and selected ownership relationships.
- Normalized source-record tables for SQL joins.
- More reviewed match candidates where needed by downstream use cases.

## Pipeline 03 follow-ons

- [x] Add a non-publishing Comtrade validation path with schema, identifier, source-reference, metadata, and configured-coverage checks.
- [x] Preserve response counts, content hashes, and source-vintage/revision fields in the published product manifest when exposed by the source.
- [ ] Validate the live UN Comtrade connector and subscription/coverage behavior against the configured account and target reporter.
- [ ] Add broader country/product coverage and an explicit refresh cadence after live coverage is reviewed.
- Keep company-level attribution out of scope unless supported by separate
  company-specific evidence.

## Pipeline 04 — public awards pilot

- [x] USAspending award search with bounded pagination and raw capture per page.
- [x] Transaction (modification) history for the top N awards as `award_events`.
- [x] Separate obligation, outlay, and announced amounts and dates.
- [x] Recipient grouping by UEI, unreviewed Pipeline 01 match candidates, classification tags, and recipient HHI.
- [x] Non-publishing `validate-usaspending` command; local and PostgreSQL publication tested with fixtures.
- [x] Five defense/technology sector presets (`config/award_sectors.yaml`, `--sector`) and an `--awarding-agency` filter.
- [x] Quarterly obligation trends, de-obligation flags, and new-entrant flags.
- [ ] Live API validation and reviewer sign-off for the selected sectors.
- [ ] One non-US portal after source-policy review; SAM.gov solicitations.

## Pipeline 05 — multilingual events prototype

- [x] GDELT DOC article discovery with URL canonicalization and syndication handling.
- [x] Rule-based headline event candidates with exact evidence spans and recorded extractor identity.
- [x] Evidence-support, candidate-status, and extractor gates; entity mention edges and event signal counts.
- [x] Non-publishing `validate-gdelt` command; local and PostgreSQL publication tested with fixtures.
- [x] Five sector query presets aligned with Pipeline 04 and award recipients accepted as `--entities`.
- [ ] Live API validation.
- [ ] Local LLM extractor, labeled evaluation set, and canary comparison against the rules.
- [ ] Primary-source follow-up allowlist and analyst review for verified events.

## Later Spec 0001 phases

- Facility activity and other signals identified as later-phase work in the
  parent specification.
