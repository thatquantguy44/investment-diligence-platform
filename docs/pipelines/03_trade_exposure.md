# Pipeline 03 — Trade and supply-chain exposure

The bounded pilot normalizes annual or monthly UN Comtrade-compatible records for one reporter and a configurable HS-code basket. It publishes `trade_flows`, `product_country_exposure`, `partner_concentration`, and `mirror_trade_discrepancies` with raw capture lineage and an explicit coverage report.

See the [UN Comtrade source runbook](../sources/un_comtrade.md) for credentials, preview versus subscription access, and terms considerations.

## Approval worksheet: reporter countries and HS baskets

**Status:** Initial scope selected; live validation and final reviewer sign-off
remain pending.

Pipeline 03 begins with one selected reporter country and one selected sector
basket. Record the decision here before using a broader live query.
Reporter codes are UN Comtrade codes, not ISO country codes. HS baskets must
also record the classification version because classifications and converted
historical series can differ by source and period.

### Country candidates

| Country | UN Comtrade reporter code | Candidate rationale | Approval status |
| --- | ---: | --- | --- |
| USA | `842` | Already live-tested in this repository | **Selected for validation** |
| China | `156` | Large manufacturing and export base | Candidate |
| Germany | `276` | Industrial and automotive exposure | Candidate |
| Japan | `392` | Advanced manufacturing and electronics | Candidate |
| Republic of Korea | `410` | Batteries, semiconductors, and electronics | Candidate |
| India | `699` | Large emerging manufacturing base | Candidate |
| Netherlands | `528` | European logistics and trade hub | Candidate |
| United Kingdom | `826` | Aerospace, life sciences, and services | Candidate |
| Canada | `124` | Energy, minerals, and manufacturing | Candidate |
| Austria | `040` | Small bounded pilot option | Candidate |

### Sector basket candidates

These are starter baskets, not final sector definitions. Begin with one basket
and keep the first live run narrow.

| Sector | Starter HS codes | Classification version | Approval status |
| --- | --- | --- | --- |
| Lithium-ion batteries | `850760` | To be confirmed before approval | Candidate |
| EV supply chain | `850760`, `870380` | To be confirmed before approval | Candidate |
| Semiconductors and microelectronics | `8541`, `8542` | Initial selected basket; confirm returned HS vintage during live validation | **Selected for validation** |
| Telecom equipment | `8517` | To be confirmed before approval | Candidate |
| Medical devices | `9018` | To be confirmed before approval | Candidate |
| Aerospace | `8802`, `8803` | To be confirmed before approval | Candidate |
| Industrial automation | `8479`, `8537` | To be confirmed before approval | Candidate |
| Renewable power equipment | `8504`, `8541` | To be confirmed before approval | Candidate |

### Decision record

- Selected country: United States
- Selected reporter code: `842`
- Selected sector: Semiconductors and microelectronics
- Selected HS codes: `8541`, `8542`
- HS classification version: Confirm from the live UN Comtrade response before final sign-off
- Period or date range:
- Partner scope, default `0` / World:
- Flow scope, default imports and exports:
- Reviewer:
- Review date:
- Coverage and access notes:

The selected scope is the active non-publishing validation configuration. It
does not become a publishing production scope until the remaining decision
record, live coverage check, and reviewer sign-off are completed.

## Offline fixture replay

```bash
PYTHONPATH=src python -m diligence_pipelines.cli run 03_trade_exposure \
  --period 2024 \
  --reporter-code 842 \
  --hs-code 850760 \
  --trade-fixture tests/fixtures/trade_flows.json
```

The fixture is synthetic and is intended for deterministic tests. Use `DILIGENCE_STORAGE_BACKEND=postgres` to publish the same output tables to the configured `IDP` database.

## Non-publishing validation

Before publishing a live response, validate its shape and observed coverage without writing to storage:

```bash
PYTHONPATH=src python -m diligence_pipelines.cli validate-comtrade \
  --period 2024 \
  --reporter-code 842 \
  --hs-code 850760 \
  --trade-fixture tests/fixtures/trade_flows.json
```

The command reports the response hash, row count, source-vintage/revision metadata, coverage, and quality checks. It exits non-zero when configured HS codes are missing or another check fails, and never writes raw or curated data. The publishing path records the same source metadata in its product manifest.

## Live connector path

Without `--trade-fixture`, the pipeline calls the configurable `COMTRADE_API_URL` using `COMTRADE_API_KEY` when supplied:

```bash
COMTRADE_API_KEY="..." PYTHONPATH=src python -m diligence_pipelines.cli run 03_trade_exposure \
  --period 2024 \
  --reporter-code 842 \
  --hs-code 850760
```

The initial connector uses the public UN Comtrade preview endpoint. Confirm the applicable subscription tier, quota, terms, reporter coverage, and HS-code vintage before using a production dataset.

## Formulas and controls

- Partner share = partner trade value / total trade value for `(period, reporter, HS code, flow)`.
- Partner HHI = `sum(partner share²) × 10,000`.
- Mirror discrepancy ratio = `abs(reported export − counterpart mirror import) / max(reported export, counterpart mirror import)`.

The manifest records observed and configured HS codes, missingness, counterpart coverage, source hashes, source-vintage/revision metadata, and limitations. These aggregates do not establish named-company import/export activity. Mirror differences can reflect timing, valuation, routing, re-exports, units, or reporting coverage.
