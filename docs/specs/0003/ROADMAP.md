# Spec 0003 Roadmap

This roadmap is deliberately provisional. No implementation should begin until
the source and use-case boundary is agreed.

## Discovery backlog

- Identify one concrete WIFO dataset and one concrete CNIPA dataset or endpoint.
- Define the diligence question and minimum normalized fields for each.
- Review access terms, language, geography, licensing, rate limits, and evidence
  retention requirements.
- Decide whether either source belongs in an existing pipeline or needs a new
  bounded pipeline slice.
- Create fixtures and a source runbook before any live collection.

## Deferred

- Connectors, scheduling, entity resolution, broad historical backfills, and
  production publication.
