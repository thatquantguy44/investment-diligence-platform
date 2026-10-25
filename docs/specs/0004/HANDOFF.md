# Spec 0004 Handoff

## Current state

The [specification](0004-controlled-bulk-source-discovery.md) is a draft for
review. Metadata discovery has been implemented; no live release approval is
implied. The existing analyst review, refresh preparation, and Dagster
definitions remain as described in the [source runbook](../../sources/uspto_odp.md).

On 2026-10-25 the official search and product detail endpoints were verified
live. Two-step metadata-only discovery now resolves one exact `PVGPATDIS` /
`g_patent.tsv.zip` candidate, preserves both raw captures, and writes the
configured path once. The latest local evidence is
`.data/uspto/odp_discovery.json`. No patent ZIP was downloaded.

## Next handoff

Implement immutable approval binding and download validation in
[ROADMAP.md](ROADMAP.md). Review quarterly freshness thresholds, then present
the exact candidate to the analyst and record explicit approval before a
manual Dagster refresh. Keep the six-hour schedule disabled until that
acceptance test passes.
