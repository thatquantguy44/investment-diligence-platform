# Spec 0004 Handoff

## Current state

The [specification](0004-controlled-bulk-source-discovery.md) is under
implementation. Metadata discovery, immutable approval records on the
persistent USPTO artifact volume, pre-download validation, and an audited
Dagster retry path are implemented. No successful prepared live release exists.

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
The release is already `stale_review_required` at 198 days old. This host
discovery preceded the approval and Dagster run described below.

A one-off container built from the Dagster image reran metadata-only discovery
on the persistent `investment_diligence_uspto_artifacts` volume. Its immutable
snapshot ID is `aff64905-191f-48e7-99d2-2bcf44142a08`, stored under
`/var/lib/diligence/uspto/discoveries/`. The exact snapshot and both
content-addressed PostgreSQL captures passed read-back and hash verification.
The candidate fingerprint matches the host discovery above. An ignored local
review bundle with the exact deployed snapshot, both source captures, and a
human-readable summary is under `.data/uspto/deployed_review/aff64905-191f-48e7-99d2-2bcf44142a08/`.
The one-off container runs as OS user `root`; its approval record names that
container actor separately from reviewer Joshua Lutkemuller. No background
Dagster service or six-hour schedule has been started.

Joshua Lutkemuller explicitly approved the deployed candidate for one manual
Dagster download-and-prepare run. Approval
`1f412a84-90b2-4270-95a9-146f4627d7be` was recorded on the persistent
volume with container OS actor `root`. Dagster run
`a05cff8c-5b8c-49ca-984d-a743860e4fae` failed before download because
the official file endpoint returned HTTP 302 to a signed `data.uspto.gov`
URL. No artifact was saved; the patent index count remained 9,454,161 before
and after the run. The code now permits only that exact signed redirect
without forwarding the API key, under
source-policy version `uspto-odp-pvgpatdis-g-patent-v2`. The prior approval
remains a failed audit record and cannot authorize this changed policy.

The rebuilt Dagster image reran metadata-only discovery under policy v2 on the
persistent volume. Its immutable discovery ID is
`2276e751-9788-48e1-afd8-d3a7320dc83c` and candidate fingerprint is
`sha256:61c906dca9bf2b3e81638265d8e142cd2bcf981ab30c7c04095b97a88755f4dd`.
The exact snapshot and both PostgreSQL captures passed read-back and hash
verification. The previous approval pointer still exists for audit but fails
validation under v2. A new ignored local
review bundle is under `.data/uspto/deployed_review/2276e751-9788-48e1-afd8-d3a7320dc83c/`.

Joshua Lutkemuller approved this v2 revision for one manual run. Approval
`b3e5f70e-3fcd-4c9b-9d37-1cda8dba17a9` was recorded and validated.
Dagster run `94b92b7f-8312-4052-8f19-9870d114b771` failed with HTTP 403
during file download; no ZIP was saved and the patent index count remained
9,454,161. A subsequent no-body-read API diagnostic returned HTTP 429, so
further source requests were stopped. The failure report and run summary are
in the review bundle. Error handling now distinguishes an HTTP failure at the
official API endpoint from one at the signed file host without exposing the
signed URL. Joshua Lutkemuller authorized one audited retry of this approval
after a metadata-only health check confirms the official file endpoint has
recovered to the expected signed redirect. Subsequent sparse no-body-read
checks still returned HTTP 429 with no `Retry-After`; no retry was recorded or
run while throttling continued.

## Next handoff

Wait for the source to recover from throttling. The one retry authorization
for v2 approval `b3e5f70e-3fcd-4c9b-9d37-1cda8dba17a9` is conditional on a
metadata-only health check showing the expected signed redirect. The Dagster
image already includes safer failure-stage reporting. Once healthy, request
the audited retry with the analyst rationale and run one manual Dagster
refresh. Verify the artifact and unchanged index count. Do not make another
attempt after that without a new analyst decision.
Review the `stale_review_required` status before considering manual ingestion
or presenting the data as current.
Keep the six-hour schedule disabled until that acceptance test passes.
