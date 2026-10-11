# Pipeline 03 — Trade and supply-chain exposure

The bounded pilot normalizes annual or monthly UN Comtrade-compatible records for one reporter and a configurable HS-code basket. It publishes `trade_flows`, `product_country_exposure`, `partner_concentration`, and `mirror_trade_discrepancies` with raw capture lineage and an explicit coverage report.

See the [UN Comtrade source runbook](../sources/un_comtrade.md) for credentials, preview versus subscription access, and terms considerations.

## Offline fixture replay

```bash
PYTHONPATH=src python -m diligence_pipelines.cli run 03_trade_exposure \
  --period 2024 \
  --reporter-code 842 \
  --hs-code 850760 \
  --trade-fixture tests/fixtures/trade_flows.json
```

The fixture is synthetic and is intended for deterministic tests. Use `DILIGENCE_STORAGE_BACKEND=postgres` to publish the same output tables to the configured `IDP` database.

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

The manifest records observed and configured HS codes, missingness, counterpart coverage, source hashes, and limitations. These aggregates do not establish named-company import/export activity. Mirror differences can reflect timing, valuation, routing, re-exports, units, or reporting coverage.
