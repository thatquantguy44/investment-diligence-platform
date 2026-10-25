# Spec 0004 Handoff

## Current state

The [specification](0004-controlled-bulk-source-discovery.md) is a draft for
review. No implementation or live release approval is implied. Existing ODP
discovery, analyst review, refresh preparation, and Dagster definitions remain
as described in the [source runbook](../../sources/uspto_odp.md).

The 2026-10-25 live catalog search authenticated successfully. The configured
title returned no candidate, while a broader product search found the stable
`PVGPATDIS` identifier. The search response did not include file URLs. A prior
local product-detail capture contains `g_patent.tsv.zip`. The current discovery
code therefore needs product detail resolution, realistic response fixtures,
and a path fix before it can support a reliable manual acceptance test.

## Next handoff

Review the product and artifact policy, immutable approval contract, download
validation, and quarterly freshness thresholds in the spec. Then implement
the ordered work in [ROADMAP.md](ROADMAP.md), run a fresh metadata-only
discovery, present the exact candidate to the analyst, and record explicit
approval before a manual Dagster refresh. Keep the six-hour schedule disabled
until that acceptance test passes.
