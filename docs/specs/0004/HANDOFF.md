# Spec 0004 Handoff

## Current state

The [specification](0004-controlled-bulk-source-discovery.md) is under
implementation. Metadata discovery, immutable approval records on the
persistent USPTO artifact volume, pre-download validation, and an audited
Dagster retry path are implemented. No live release approval is implied.

On 2026-10-25 the official search and product detail endpoints were verified
live. Two-step metadata-only discovery now resolves one exact `PVGPATDIS` /
`g_patent.tsv.zip` candidate, preserves both raw captures, and writes the
configured path once. The latest local evidence is
`.data/uspto/odp_discovery.json`. No patent ZIP was downloaded.
The refreshed local candidate is 232,076,712 bytes, with a provider release
date of 2026-04-10 and no provider checksum. Its approval policy still has
unset size and freshness limits, so it cannot be approved for a live refresh.

## Next handoff

Review and configure artifact size bounds, release age, and patent-data
freshness thresholds. Run a fresh discovery under that policy, then present
the exact candidate to the analyst for explicit approval. Test one manual
Dagster refresh with persistent storage and verify no index rows changed.
Keep the six-hour schedule disabled until that acceptance test passes.
