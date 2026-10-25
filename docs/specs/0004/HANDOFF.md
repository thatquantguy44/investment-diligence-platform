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
date of 2026-04-10 and no provider checksum. The agreed provisional policy is
150,000,000–350,000,000 bytes, warning at 150 days since release or 240 days
since the newest patent date, and blocking at 240 and 330 days respectively.
Metadata-only discovery was rerun under this policy on 2026-10-25 with both
raw captures verified in PostgreSQL. Its latest snapshot ID is
`e138d402-690e-424f-86f2-9d22bca5ed50`; the exact candidate
fingerprint is
`sha256:cb8765e09f245f50ade270e2cf5cf813eeeeb680233547465a6a24eb858dd958`.
The release is already `stale_review_required` at 198 days old. No candidate
approval, patent ZIP download, or Dagster refresh has occurred.

## Next handoff

Present the exact candidate and both captured metadata records to the analyst
for explicit approval. The manual Dagster acceptance run must use the same
persistent source-capture store and approval volume. The current host `.data`
snapshot is for inspection; rerun discovery on the mounted artifact volume
before an approval intended for the containerized Dagster runtime. Test one manual
Dagster refresh with persistent storage and verify no index rows changed.
Review the `stale_review_required` status before considering manual ingestion
or presenting the data as current.
Keep the six-hour schedule disabled until that acceptance test passes.
