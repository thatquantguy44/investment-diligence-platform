# Spec 0004: Controlled Bulk Source Discovery

**Status:** Implementation in progress; deployment policy and live acceptance pending
**Version:** 0.1.0
**Extends:** [Spec 0001](../0001/0001-investment-diligence-pipelines.md), Pipeline 02
**Owner:** Quantitative diligence / data engineering
**Last updated:** 2026-10-25

**Roadmap:** [ROADMAP.md](ROADMAP.md) | [Handoff](HANDOFF.md) | [Master roadmap](../../MASTER_ROADMAP.md)

## 1. Objective and scope

Make USPTO Open Data Portal (ODP) release discovery reliable when catalog titles,
response envelopes, file lists, or releases change. An operator should see the
exact source file and provenance before approving one download. The first
implementation targets Pipeline 02's `PVGPATDIS` product and
`g_patent.tsv.zip` artifact. The record contract should be reusable for another
bulk source, but this spec does not authorize a generic source framework or
additional connector.

The operating sequence is:

```text
bounded discovery → policy evaluation → immutable candidate → analyst approval
→ verified download preparation → explicit ingestion and publication
```

Discovery may run on a cadence only after the manual acceptance test. It may
read source metadata and record candidates. Approval is a human action;
download preparation, indexing, and catalog publication remain separate steps.

### Observed reason for this spec

On 2026-10-25 the live ODP search using the configured title
`PatentsView granted patent disambiguated` returned zero candidates. A broader
search returned product identifier `PVGPATDIS`, titled `PatentsView Granted
Patent Disambiguated Data`, but the search response contained product summaries
without file download URLs. The product detail response available from an
earlier local source capture contains `productFileBag.fileDataBag`, including
`g_patent.tsv.zip`. The current test fixture uses a different `products/files`
shape. A successful HTTP request therefore produced a misleading
`candidate_count: 0` discovery, and the explicit `.data/...` output path was
written under `.data/.data/...`.

The [USPTO ODP search documentation](https://data.uspto.gov/apis/bulk-data/search)
distinguishes product search from Product Data for a specific dataset. The
implementation must verify the detail endpoint and its response shape against
the live API before release approval. Local captures and official docs are
evidence for this design, not a promise that upstream metadata cannot change.

### Design decisions

- Use the provider's product identifier and an exact filename. Matching a
  display title or choosing the first URL is too sensitive to catalog copy and
  ordering changes.
- Keep search and product detail as separate captures. Search establishes the
  product identity; detail establishes the artifact identity and release
  metadata.
- Normalize candidates and approvals now, but implement only the USPTO
  adapter. A generic provider framework would add contracts that no second
  source has yet tested.
- Keep analyst approval tied to a material candidate revision. Repeated
  observations remain visible without repeatedly authorizing the same file.

## 2. Requirements

### Source and selection policy

- The approved source policy identifies the USPTO host, product identifier
  `PVGPATDIS`, exact artifact name `g_patent.tsv.zip`, and permitted metadata
  and download URL paths. Product title is display context, never a key.
- Search is bounded and paginated. It must find exactly one matching product
  identifier, then retrieve its product detail record and find exactly one
  matching filename. No substring or first-match fallback may approve a file.
- Pagination follows only documented response fields and approved same-origin
  HTTPS URLs. It records page count and completion. Repeated page links, a
  reached page cap with a further page, malformed responses, missing product or
  file, and duplicate matches produce a blocked discovery with a reason.
- Policy values, including expected file type, optional size bounds, accepted
  host/path, and freshness rules, are versioned. A renamed title by itself is
  recorded as a metadata change; it does not silently switch product identity.

### Discovery and evidence

- Preserve the product search and product detail raw response captures outside
  Git, each with source URL, retrieval time, status, content SHA-256, request
  parameters without secrets, adapter version, and capture path. An incomplete
  or failed capture is never presented as a complete candidate list.
- Normalize one candidate per exact product and filename. Its stable logical
  identity is `(source_id, product_identifier, artifact_name)`; its candidate
  revision fingerprint is a deterministic hash of material provider fields,
  including the canonical download URL, file size,
  file release and modification timestamps, and provider checksum if supplied,
  plus a digest of approval-relevant policy fields. The full policy version is
  recorded separately; changing documentation or unrelated policy fields
  must not revoke an approval. Canonical serialization and null handling must
  be documented and tested. Product title and unrelated catalog rows are not
  material fingerprint inputs.
- The candidate links to the immutable discovery snapshot and both raw capture
  hashes. Repeated discovery of the same material revision keeps the same
  candidate fingerprint while recording a new observation time.
- Show changes relative to the last complete snapshot as `new`, `unchanged`,
  `changed`, `removed`, or `indeterminate`. Missing/failed upstream responses
  are `indeterminate`, never evidence that a file was removed. Title-only
  changes are visible without becoming a different logical artifact.
- An explicit output path resolves to exactly that path; a configured default
  resolves once against `DILIGENCE_DATA_ROOT`. CLI and Dagster must read and
  write the same resolved path. Persistence failures block a success result.

### Approval and execution

- An authorized analyst reviews one displayed candidate. For the first
  single-reviewer deployment, the operator identity must be enforced through
  a configured reviewer and restricted runtime/file permissions; a caller
  supplied `--reviewer` name alone does not confer authority. Record the
  authenticated or OS-controlled actor identifier separately from display
  name, UTC review time, rationale, discovery ID, logical identity, candidate
  revision fingerprint, policy version, approval-relevant policy digest, and
  source capture hashes. The review command must reject an unauthorized
  actor or an incomplete, blocked, ambiguous, or modified snapshot.
- The approval record is append-only. A mutable `reviewed_selection.json` may
  point to the active approval for the existing Dagster sensor, but it is not
  the audit record. An approval is specific to one candidate revision. A
  material change requires a new approval; an unrelated catalog product change
  does not invalidate the approved revision.
- Before any download, refresh validates the approval against its stored
  candidate and current policy, including exact product ID, filename,
  fingerprint, and permitted URL. It then performs a fresh, bounded product
  detail lookup and compares material file fields with the approved revision
  immediately before the artifact request. It fails closed on missing
  provenance, tampering, revoked policy, or changed material metadata. A
  still-valid approval may be retried without granting new authority.
- Dagster uses a stable approval/candidate run key and durable execution state
  to avoid duplicate refreshes. It must not mark an approval fully consumed
  solely because a run request was emitted; interrupted or failed runs need an
  explicit, auditable retry path. The sensor does not grant approval.
- Download uses a temporary artifact. Verify byte count, supported archive
  shape, computed SHA-256, and a provider checksum when offered before making
  the prepared artifact visible. When no provider checksum exists, record
  `provider_checksum_status: unavailable`; the local SHA-256 is a preservation
  and comparison check, not provider-attested integrity. Archive and record
  quality checks must finish
  before a candidate can be marked prepared. A blocked or failed refresh must
  preserve the prior usable artifact and its lineage.
- Ingestion and publication require separate explicit commands and quality
  gates. A prepared download is not an indexed or published patent release.

### Security and operations

- USPTO metadata and artifact URLs are untrusted input. Enforce HTTPS and a
  narrow host/path allowlist on catalog, product detail, pagination, redirects,
  and download URLs. Never forward `X-Api-Key` to another origin or put it in a
  URL, raw capture, manifest, log, or alert.
- Bound pagination, request time, response size, and artifact size. Log a
  structured reason for blocked or failed operations, with discovery and
  candidate identifiers, without credential values.
- Discovery, approval, prepared, blocked, and failed states are durable and
  inspectable. Slack delivery remains a separate deployment step; no delivery
  is implied by recording an alert event.
- The six-hour Dagster discovery schedule remains inactive until a manual,
  analyst-approved end-to-end refresh acceptance test passes in the deployed
  runtime with persistent storage and secret injection, and the separately
  agreed operational alert policy is met. Slack delivery is not part of this
  spec's implementation authorization.

## 3. Proposed record contract

The implementation may add optional fields to existing CLI reports and stored
JSON. It should version normalized records rather than silently changing the
meaning of an existing field. The example below is a shape, not a live release:

```json
{
  "schema_version": "1.0.0",
  "source_id": "uspto_odp",
  "product_identifier": "PVGPATDIS",
  "product_title": "PatentsView Granted Patent Disambiguated Data",
  "artifact_name": "g_patent.tsv.zip",
  "logical_artifact_id": "uspto_odp:PVGPATDIS:g_patent.tsv.zip",
  "candidate_fingerprint": "sha256:<canonical-material-fields>",
  "policy_version": "<approved-policy-version>",
  "approval_policy_digest": "sha256:<approval-relevant-policy-fields>",
  "download_url": "https://api.uspto.gov/api/v1/datasets/products/files/PVGPATDIS/g_patent.tsv.zip",
  "size_bytes": 232076712,
  "file_release_at": "<provider value with its stated timezone or unknown>",
  "file_modified_at": "<provider value with its stated timezone or unknown>",
  "provider_checksum": null,
  "provider_checksum_status": "unavailable",
  "discovery_id": "<immutable snapshot id>",
  "search_capture_sha256": "<sha256>",
  "detail_capture_sha256": "<sha256>",
  "discovered_at": "<UTC timestamp>",
  "policy_status": "review_required",
  "policy_reasons": []
}
```

The source-native timestamps must not be silently converted to UTC if the
provider omits a timezone. Hash input must use the original normalized values
and explicit nulls. `discovered_at`, product title, unrelated catalog rows,
and volatile search ordering are excluded from the candidate fingerprint. The
discovery snapshot records its own
completion status, pagination state, capture hashes, candidate IDs, and
diagnostic reasons. Approval and refresh reports reference these identifiers
instead of copying an unvalidated URL as the sole authority.

## 4. Compatibility and migration

Keep the current CLI entry points (`discover-uspto-odp`, `review-uspto-odp`,
`refresh-uspto-odp`) and Dagster asset names during the initial migration.
Extend output fields additively where possible. Existing manually authored
selection files with only `status` and `download_url` are legacy and must be
re-reviewed before a new live refresh; do not invent missing provenance.
Existing raw patent files and the PostgreSQL index remain untouched by this
spec. Discovery history must preserve old reports and distinguish their schema
version and evidence limits from the new records.

## 5. Implementation and verification boundary

Python 3.11+, `pytest`, the existing CLI and Dagster code location remain the
implementation stack. Proposed code belongs in
`src/diligence_pipelines/sources/uspto_odp.py`, `settings.py`, `cli.py`, and
`orchestration/dagster_defs.py`; fixtures and contract tests belong in
`tests/`. Source operations stay in `docs/sources/uspto_odp.md`. Keep the
implementation specific to ODP until another bulk provider proves a common
adapter necessary.

Use Python `snake_case` for normalized fields and explicit exact-match checks
at the provider boundary. For example, the intended selection rule is:

```python
matches = [row for row in file_data_bag if row.get("fileName") == policy.artifact_name]
if len(matches) != 1:
    raise DiscoveryBlocked("target artifact is missing or ambiguous")
```

Verification commands after implementation:

```bash
PYTHONPATH=src python -m pytest -q tests/test_uspto_odp.py tests/test_cli.py tests/test_dagster_orchestration.py
PYTHONPATH=src python -m diligence_pipelines.cli validate-docs
git diff --check
```

Use sanitized, realistic `bulkDataProductBag` search and
`productFileBag.fileDataBag` detail fixtures. Test the network boundary with
mocked HTTP responses: a title rename with stable ID, exactly one target file,
missing and duplicate product/file, pagination completion and loops, wrong
hosts/redirects, provider metadata drift during the pre-download recheck, an
approval edited after review, an unauthorized reviewer, and a discovery that
invokes no downloader. Verify that title-only and unrelated catalog changes
preserve the candidate fingerprint and approval, while changed URL, size, or
release time requires reapproval. Test that a pagination cap with a next page
blocks completeness, and that download or quality failure preserves the prior
artifact and sidecar. Cover provider checksum and size mismatch, durable write
failure, one run for duplicate sensor observations, and an audited retry after
an interrupted or failed run. Test that explicit `.data/...` paths are not
doubled and match Dagster's path. One live manual acceptance run must show the
source capture, one reviewable candidate, the analyst's approval, a validated
artifact at the configured `USPTO_ODP_REFRESH_OUTPUT`, a `prepared` report at
`<output>.refresh.json` with `ingestion_status: not_started`, and unchanged
patent-index counts.

## 6. Boundaries and success criteria

- **Always:** validate external responses and URLs, preserve source evidence,
  fail closed on ambiguity, keep state transitions auditable, run the focused
  tests and documentation validator before merging implementation.
- **Review before activation:** source-policy changes, a new product/file
  target, deployment secrets, a live approval, alert delivery policy, and
  schedule enablement.
- **Never:** commit credentials or live artifacts, infer approval from discovery,
  send provider credentials across origins, or treat a prepared download as a
  published patent index.

This spec is satisfied when a live metadata-only discovery identifies exactly
one `PVGPATDIS` / `g_patent.tsv.zip` candidate with complete provenance;
ambiguous or incomplete results are blocked; repeat observations do not trigger
duplicate refreshes; one explicit approval produces one validated manual
refresh with an auditable retry path; and the prior usable artifact survives
failure. Passing a freshness rule must reflect the product's documented
quarterly cadence: file release age and newest patent-data date are distinct
measurements, and their thresholds must be reviewed before acceptance.

## 7. Open decisions for review

1. The first acceptance run uses provisional 150,000,000–350,000,000 byte
   bounds for `PVGPATDIS/g_patent.tsv.zip`. Review observed release variation
   before treating those bounds as steady-state policy.
2. The first acceptance run warns after 150 release-age days or 240 patent-data
   age days, and blocks after 240 or 330 days respectively. Unknown or future
   newest patent dates block preparation. A stale but allowed file can be
   prepared with a review-required label; it must not be presented as current
   without analyst review. Reassess these thresholds from release history.
3. Immutable approval records use the persistent USPTO artifact volume with
   private OS permissions. The supersession policy still needs analyst review.
4. Which sanitized source capture should become the checked-in contract
   fixture after validating the current live detail endpoint?

## 8. Sources

- [USPTO ODP bulk product search API](https://data.uspto.gov/apis/bulk-data/search)
- [USPTO Open Data Portal access and account guidance](https://www.uspto.gov/subscription-center/2026/register-access-usptos-open-data-portal)
- [Pipeline 02 ODP operations runbook](../../sources/uspto_odp.md)
