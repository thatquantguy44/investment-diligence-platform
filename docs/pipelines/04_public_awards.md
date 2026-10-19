# Pipeline 04 — Public awards, procurement, and grants

The bounded pilot normalizes US federal contract or grant awards from
USAspending for one action-date window and one sector filter (NAICS, PSC, or
keywords). It retains each award's modification history, keeps obligation and
outlay amounts separate, groups recipients by UEI, and publishes recipient
concentration plus classification tags. Every normalized award links back to
its original USAspending award page and raw capture.

See the [USAspending source runbook](../sources/usaspending.md) for access,
rate limits, and field semantics.

## Outputs

| Output | Grain | Notes |
| --- | --- | --- |
| `awards` | One row per `generated_internal_id` | Obligated, outlay, and (always null) announced amounts kept separate; performance and base-obligation dates; agency hierarchy; NAICS/PSC/assistance listing; `source_url` to the original record |
| `award_events` | One row per USAspending transaction | Modification number, action type, action date, federal action obligation; fetched for the top `--max-transaction-awards` awards |
| `recipient_entities` | One row per recipient UEI (falls back to recipient hash, then normalized name) | Name variants, award count, total obligation, unreviewed Pipeline 01 match candidates when `--entities` is supplied |
| `technology_program_tags` | One row per award × classification code | Source classifications only (`naics`, `psc`, `assistance_listing`); no inferred technology labels |
| `recipient_concentration` | One row per award group × NAICS (or PSC) code | Recipient HHI on obligations, top-recipient share |

`solicitations` from the Spec 0001 output list is not implemented: USAspending
does not publish solicitations, and SAM.gov opportunities need a separate key
and source review.

## Approval worksheet: sector filter

**Status:** Candidate options only — no sector is approved yet.

Pipeline 04 starts with one award group, one sector filter, and one action-date
window. Record the decision here before a broader live pull. NAICS codes changed
between the 2017 and 2022 vintages (for example, batteries moved from
`335911` to `335910`); confirm the vintage before approval.

| Sector | Award group | Starter filter | Approval status |
| --- | --- | --- | --- |
| Semiconductors | contracts | NAICS `334413`; PSC `5961`, `5962` | Candidate (fixture uses this) |
| Lithium-ion batteries | contracts | NAICS `335910`, `335911` | Candidate |
| Aerospace | contracts | NAICS `336411`, `336413`, `336414` | Candidate |
| Medical devices | contracts | NAICS `339112`, `334510` | Candidate |
| Industrial automation | contracts | NAICS `333249`, `335314` | Candidate |
| Semiconductor R&D grants | grants | Keywords such as `semiconductor`, `CHIPS` | Candidate |

### Decision record

- Approved award group:
- Approved NAICS / PSC codes or keywords:
- Action-date window:
- `--max-results` and `--max-transaction-awards` bounds:
- Reviewer:
- Review date:
- Coverage and access notes:

## Offline fixture replay

```bash
PYTHONPATH=src python -m diligence_pipelines.cli run 04_public_awards \
  --awards-fixture tests/fixtures/usaspending_awards.json \
  --entities tests/fixtures/entity_graph.jsonl
```

The fixture is synthetic. Use `DILIGENCE_STORAGE_BACKEND=postgres` to publish
the same outputs to `diligence.awards`, `diligence.award_events`,
`diligence.recipient_entities`, `diligence.technology_program_tags`, and
`diligence.recipient_concentration`.

## Non-publishing validation and live path

```bash
PYTHONPATH=src python -m diligence_pipelines.cli validate-usaspending \
  --award-group contracts --start-date 2024-01-01 --end-date 2024-12-31 \
  --naics 334413 --max-results 50

PYTHONPATH=src python -m diligence_pipelines.cli run 04_public_awards \
  --award-group contracts --start-date 2024-01-01 --end-date 2024-12-31 \
  --naics 334413 --max-results 50 --max-transaction-awards 10 \
  --entities .data/curated/01_entity_graph/<run_id>/entities.jsonl
```

A live run requires a date window and at least one `--naics`, `--psc`, or
`--keyword` filter. The live connector has been unit-tested against mocked
responses but has not yet been run against the real API from this repository.

## Formulas and quality gates

- Recipient obligation share = recipient obligation / total obligation for `(award group, NAICS or PSC code)`.
- Recipient HHI = `sum(recipient share²) × 10,000`; null when total obligation is zero.

Publication is blocked when award IDs repeat, required fields or source
references are missing, a transaction references an award outside the run, or
the API returns an error. A truncated result (more matches than
`--max-results`) is a warning recorded in the coverage report.

## Controls and limitations

- An award or obligation is not evidence of contract performance, payment, revenue, or product-market fit.
- Obligations are commitments and can be de-obligated; outlays are disbursements. Neither is an announced amount.
- Recipient-to-entity matches are unreviewed name-similarity candidates; they never confirm a Pipeline 01 entity.
- The award search returns current award state. Use `award_events` for the amendment history.
