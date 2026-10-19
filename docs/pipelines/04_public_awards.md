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
| `award_events` | One row per USAspending transaction | Modification number, action type, action date, federal action obligation, `is_deobligation` (negative obligation); fetched for the top `--max-transaction-awards` awards |
| `recipient_entities` | One row per recipient UEI (falls back to recipient hash, then normalized name) | Name variants, award count, total obligation, first base-obligation date, `new_entrant_in_window`, de-obligation count and amount, unreviewed Pipeline 01 match candidates when `--entities` is supplied |
| `technology_program_tags` | One row per award × classification code | Source classifications only (`naics`, `psc`, `assistance_listing`); no inferred technology labels |
| `recipient_concentration` | One row per award group × NAICS (or PSC) code | Recipient HHI on obligations, top-recipient share |
| `obligation_trends` | One row per recipient or classification × calendar quarter | Net obligation, de-obligation total, and action count from `award_events` |

`solicitations` from the Spec 0001 output list is not implemented: USAspending
does not publish solicitations, and SAM.gov opportunities need a separate key
and source review.

## Approval worksheet: sector filter

**Status:** Five defense and technology sectors selected; each still needs a
live `validate-usaspending` run and a reviewer sign-off before broader pulls.

Each sector is a named preset in
[`config/award_sectors.yaml`](../../config/award_sectors.yaml), run with
`--sector <name>`. Explicit `--naics`, `--psc`, and `--keyword` flags are added
to the preset. USAspending ANDs different filter types and ORs codes within one
type, so presets use NAICS only (plus keywords where noted); the PSC column is
reference for a narrower follow-up run. Add `--awarding-agency "Department of
Defense"` to restrict any sector to DoD awards.

| # | Sector preset | NAICS | Keywords | Reference PSC | Pipeline 03 HS | Status |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | `semiconductors_microelectronics` | `334413` | — | `5961`, `5962` | `8541`, `8542` | Selected |
| 2 | `aerospace_missiles_space` | `336411`, `336412`, `336413`, `336414`, `336415`, `336419` | — | `1410`, `1420`, `1510`, `1520`, `1810` | `8802`, `8803` | Selected |
| 3 | `defense_electronics_sensing` | `334511`, `334220` | — | `5840`, `5841`, `5865` | `8526`, `8517` | Selected |
| 4 | `defense_rd` | `541715`, `541713` | — | — | — | Selected |
| 5 | `ai_cyber_software` | `541511`, `541512`, `541519`, `518210` | `artificial intelligence`, `machine learning`, `cybersecurity`, `autonomy` | — | — | Selected |

Why these five:

1. **Semiconductors and microelectronics:** trusted foundry, rad-hard parts, and CHIPS-era supply-chain priority; maps directly to Pipeline 03 HS baskets.
2. **Aerospace, missiles, and space:** aircraft, engines, guided missiles, space vehicles, and their parts; the largest defense hardware category.
3. **Defense electronics, sensing, and communications:** radar, sonar, navigation, guidance, electronic warfare (NAICS `334511`), and tactical radio (`334220`).
4. **Defense and deep-tech R&D:** physical-science, engineering, and nanotechnology R&D contracts (DARPA, service labs, DOE); early signal for emerging technology.
5. **AI, cyber, and mission software:** IT-services NAICS narrowed by keywords; these codes are otherwise very large and noisy.

Runners-up, not selected: shipbuilding (`336611`), combat vehicles (`336992`),
ammunition and ordnance (`332993`, `332994`), and batteries (`335910`).

### Decision record

- Selected sectors: the five presets above.
- Award group: contracts.
- Action-date window: to be set at first live validation (suggested: 2024-01-01 to 2024-12-31).
- `--max-results` and `--max-transaction-awards` bounds: suggested 100 and 10 per sector.
- Reviewer:
- Review date:
- Coverage and access notes: pending live validation; record the truncation flag and returned row count per sector.

### Validation commands

```bash
for sector in semiconductors_microelectronics aerospace_missiles_space \
  defense_electronics_sensing defense_rd ai_cyber_software; do
  PYTHONPATH=src python -m diligence_pipelines.cli validate-usaspending \
    --sector "$sector" --start-date 2024-01-01 --end-date 2024-12-31 \
    --max-results 100
done
```

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
  --sector defense_electronics_sensing --awarding-agency "Department of Defense" \
  --start-date 2024-01-01 --end-date 2024-12-31 \
  --max-results 50 --max-transaction-awards 10 \
  --entities .data/curated/01_entity_graph/<run_id>/entities.jsonl
```

A live run requires a date window and `--sector` or at least one `--naics`,
`--psc`, or `--keyword` filter. The live connector has been unit-tested against mocked
responses but has not yet been run against the real API from this repository.

## Formulas and quality gates

- Recipient obligation share = recipient obligation / total obligation for `(award group, NAICS or PSC code)`.
- Recipient HHI = `sum(recipient share²) × 10,000`; null when total obligation is zero.
- Quarterly net obligation = `sum(federal_action_obligation)` by action-date calendar quarter, per recipient and per classification; de-obligation total sums the negative actions only.
- `new_entrant_in_window` = the recipient's earliest base-obligation date in this pull is on or after `--start-date`; null when no base date is known.

Publication is blocked when award IDs repeat, required fields or source
references are missing, a transaction references an award outside the run, or
the API returns an error. A truncated result (more matches than
`--max-results`) is a warning recorded in the coverage report.

## Controls and limitations

- An award or obligation is not evidence of contract performance, payment, revenue, or product-market fit.
- Obligations are commitments and can be de-obligated; outlays are disbursements. Neither is an announced amount.
- Recipient-to-entity matches are unreviewed name-similarity candidates; they never confirm a Pipeline 01 entity.
- The award search returns current award state. Use `award_events` for the amendment history.
- Trends cover only awards whose transaction history was fetched (`--max-transaction-awards`), so they understate sector totals.
- `new_entrant_in_window` is relative to this pull, not to the recipient's full federal history.
- `recipient_entities.jsonl` can be passed to Pipeline 05 as `--entities` to link award recipients to news events.
