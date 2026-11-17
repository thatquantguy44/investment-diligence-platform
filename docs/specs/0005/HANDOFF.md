# Spec 0005 Handoff

## Current state

The [specification](0005-private-market-source-ingestion.md) scopes investor
and market mapping in Southeast Asia and nearby markets for semiconductors,
sensors, and maritime systems. Crunchbase, FundComb, and OpenVC access rights
remain source-specific gates.

An offline FundComb manual-map pilot is implemented as `map-fundcomb-csv`.
It validates a locally curated profile CSV, emits unreviewed profile claims,
and reports sample counts. It does not fetch pages, publish curated products,
or estimate funding flows. The public-profile sample of six rows is local
under ignored `.data/`; no source data is committed.

## Verification

On 2026-11-17, `PYTHONPATH=src .venv/bin/python -m pytest -ra
--override-ini addopts=''` passed 135 tests with 2 optional Dagster skips.
`validate-manifests`, `validate-docs`, and `git diff --check` pass. The focused
test is `tests/test_fundcomb_manual.py`.

## Incomplete

- FundComb Data API entitlement, response rights, rate limits, and retention
  have not been verified.
- Sensor and maritime profile coverage remains unestablished in the small
  public-search sample.
- Crunchbase and OpenVC collection are not implemented.
- No firm-level supplier, buyer, or financing-flow claims are produced.

## Next step

Expand the reviewed manual sample from permitted profile sources or obtain a
FundComb Data API entitlement. Confirm the provider rights before a live
collector or curated publication is built.
