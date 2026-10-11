# Spec 0002 Handoff

## Current state

Spec 0002 is drafted but not implemented. It defines two bounded future slices:

- Country-level procurement and grant notices.
- Company career-page signals.

No live source collection should begin until the source boundary, access terms,
and pilot scope are approved.

## Procurement and grant notices

The next decision is to select exactly one country and one sector. After that,
the implementation should identify official portals, preserve original-language
notices, extract awardee/buyer/amount/date/project/location fields, and retain
field-level evidence. Ambiguous awardees should remain unresolved candidates
against Pipeline 01.

## Company career pages

The next decision is to approve a company/domain allowlist and confirm that
collection is permitted. The future pipeline should preserve permitted page
evidence, track postings by function and location, and distinguish observed
posting changes from hiring, headcount, or expansion claims.

## Validation boundary

Spec 0002 has no active pipeline or live connector yet. Its detailed backlog is
in [`ROADMAP.md`](ROADMAP.md); repository-wide sequencing is in
[`docs/MASTER_ROADMAP.md`](../../MASTER_ROADMAP.md).
