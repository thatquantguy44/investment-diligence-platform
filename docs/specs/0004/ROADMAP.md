# Spec 0004 Roadmap

**Status:** Implementation in progress. The USPTO search and product-detail
endpoint have been verified live; realistic metadata fixtures, exact
`PVGPATDIS` / `g_patent.tsv.zip` selection, capture lineage, and a successful
metadata-only live discovery are in place. Approval binding, download guards,
and audited retry logic are implemented in code. Analyst-reviewed size and
freshness limits and a live manual acceptance run remain pending. See the
[specification](0004-controlled-bulk-source-discovery.md).

1. Confirm the current USPTO product-detail endpoint and sanitize realistic
   search and detail captures for deterministic tests. Record the approved
   product ID, exact file name, and source-policy version.
2. Implement bounded, complete two-step discovery and normalized candidate
   fingerprints. Fix path resolution shared by CLI and Dagster. Verify zero,
   duplicate, incomplete pagination, and metadata-drift behavior.
3. Bind immutable analyst approvals to candidate revisions and source
   snapshots. Enforce the configured operator identity and protected approval
   storage. Reject legacy URL-only approvals before live download; preserve an
   append-only review audit and a retryable execution state.
4. Recheck product detail immediately before downloading and block material
   drift. Validate hosts, redirects, byte count, archive and checksum before
   preparing an artifact. Preserve the previous usable release on any failure.
   Review freshness policy against the actual quarterly cadence.
5. Run one manual, analyst-approved Dagster refresh using runtime-injected
   USPTO/PostgreSQL secrets and persistent storage. Verify report and lineage
   without automatic ingestion. Record the acceptance evidence.
6. Separately decide and authorize failed/blocked alert delivery. Enable the
   six-hour discovery schedule only after the manual acceptance test passes
   and the agreed operational alert policy is met.

The Slack webhook scaffold remains inactive. Later providers may adopt the
normalized candidate and approval contract. Additional provider adapters,
automatic approval, automatic indexing, and automatic publication are outside
this spec.
