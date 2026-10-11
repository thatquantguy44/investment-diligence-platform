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

## Later Spec 0001 phases

- Public awards and procurement signals.
- Multilingual events and notices.
- Facility activity and other signals identified as later-phase work in the
  parent specification.
