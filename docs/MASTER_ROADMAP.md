# Master Roadmap

This is the cross-spec roadmap for the investment diligence pipeline
repository. Individual spec roadmaps contain the detailed backlog for that
spec; this file records sequencing and dependencies across the repository.

## Status legend

- **Complete:** implemented and tested within the current boundary.
- **In progress:** actively being built or hardened.
- **Planned:** agreed work that is not yet started.
- **Deferred:** intentionally lower priority; do not expand current scope until the prerequisite work is stable.

## Current state

| Area | Status | Current boundary |
| --- | --- | --- |
| Pipeline 01 — Entity graph | Complete for pilot | SEC EDGAR watchlist, optional GLEIF enrichment, provenance, quality gates, local/PostgreSQL publication |
| Pipeline 02 — Technology and talent | Complete for pilot slice; hardening in progress | OpenAlex research metadata plus USPTO ODP-backed local patent index |
| USPTO ODP release discovery | In progress | Scheduled catalog discovery and candidate snapshots; no automatic download or ingestion |
| Pipeline 03 — Trade exposure | Pilot | Bounded UN Comtrade-compatible country/product aggregates with coverage reporting |
| Spec 0002 procurement signals | Planned | One country and one sector must be selected before implementation |
| Spec 0002 career-page signals | Planned | Source permission and company allowlist must be defined before collection |

## Ordered roadmap

### 1. Finish Pipeline 02 operational hardening — In progress

- Run scheduled USPTO ODP release discovery from the repository wrapper.
- Reviewed selection, checksum-aware download preparation, release diffs, and
  release quality checks are implemented; PostgreSQL ingestion remains explicit.
- Finish full-release ingestion at production scale, alerting, and operational
  scheduling around approved refreshes.
- Keep OpenAlex and USPTO lineage explicit in every materialization.

### 2. Stabilize the shared operating layer — Planned

- Add migrations for PostgreSQL schema changes.
- Add structured run history, stale-source alerts, and failure notification.
- Add a consumer adapter for product manifests and contract versions.
- Select the approved production scheduler/object-store deployment.

### 3. Pipeline 02 lower-priority research backlog — Deferred

- Generate assignee-to-entity and inventor-to-entity match candidates against
  Pipeline 01.
- Add explicit match confidence, evidence, review state, and analyst workflow.
- Add richer time-windowed patent/research counts and topic observations.
- Add OpenAlex snapshot/backfill support and source-vintage comparisons.

These items must not infer current ownership, employment, technology quality, or
company affiliation from an assignee, inventor, institution, or publication
record alone.

### 4. Complete Pipeline 01 follow-ons — Planned

- SEC XBRL facts and selected ownership relationships.
- Normalized source-record joins for downstream consumers.
- Additional reviewed entity-match candidates where the business case requires them.

### 5. Build Spec 0002 bounded slices — Planned

- Choose one country and one sector for procurement/grant notices.
- Complete source-policy and access review for the selected official portals.
- Build the procurement notice evidence product with unresolved-match handling.
- Define an approved company career-page allowlist, then build posting snapshots,
  role counts, and observed changes with stale/duplicate controls.

### 6. Later expansion — Deferred

- Additional countries, sectors, and portals.
- Broad career-page coverage beyond an approved allowlist.
- More advanced entity resolution or automated investment conclusions.
- Facility activity and other signals identified as later-phase work in Spec 0001.

## Detailed roadmaps

- [Spec 0001 roadmap](specs/0001/ROADMAP.md)
- [Spec 0002 roadmap](specs/0002/ROADMAP.md)
