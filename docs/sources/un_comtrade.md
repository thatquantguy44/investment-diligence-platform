# UN Comtrade

## Purpose

Pipeline 03 uses country/product trade aggregates to measure exposure and concentration for a bounded HS-code basket. It publishes trade flows, partner shares, HHI concentration, mirror discrepancies, and coverage/missingness metadata.

## Access and credentials

The current adapter defaults to the UN Comtrade preview endpoint. Preview calls do not require an account or API key but have limited endpoints, record counts, and rate limits.

For broader API access, bulk files, or higher limits, obtain a UN Comtrade subscription key and configure:

```yaml
COMTRADE_API_KEY: "your-key-here"
COMTRADE_API_URL: "https://comtradeapi.un.org/public/v1/preview/C/A/HS"
```

The key belongs in the ignored local variables file or environment only. Do not place it in the React app.

## Bounded run examples

Offline fixture replay:

```bash
PYTHONPATH=src python -m diligence_pipelines.cli run 03_trade_exposure \
  --period 2024 \
  --reporter-code 842 \
  --hs-code 850760 \
  --trade-fixture tests/fixtures/trade_flows.json
```

Preview/live connector path:

```bash
PYTHONPATH=src python -m diligence_pipelines.cli run 03_trade_exposure \
  --period 2024 \
  --reporter-code 842 \
  --partner-code 0 \
  --flow-code M,X \
  --hs-code 850760
```

Repeat `--hs-code` for a configured sector basket. Use `YYYY` for annual periods and `YYYYMM` for monthly periods when supported by the selected endpoint.

## Outputs and formulas

- Partner share = partner trade value / total trade value for `(period, reporter, HS code, flow)`.
- Partner HHI = `sum(partner share²) × 10,000`.
- Mirror discrepancy ratio = `abs(reported export − counterpart mirror import) / max(reported export, counterpart mirror import)`.

The product manifest records configured and observed HS codes, missingness, mirror-pair coverage, source hash, and limitations.

## Controls and limitations

- Country/product aggregates do not establish named-company import/export activity.
- Track reporter coverage, partner coverage, flow direction, units, re-exports, revisions, and HS-code classification vintage.
- Mirror differences can reflect timing, valuation, routing, re-exports, units, or reporting coverage.
- `un_comtrade_fixture` and `trade_flows.json` are synthetic test inputs.
- Confirm the current subscription tier, quota, and data-use terms before production use.

## Official references

- [UN Comtrade API](https://uncomtrade.org/docs/un-comtrade-api/)
- [UN Comtrade subscription plans](https://uncomtrade.org/docs/subscriptions/)
- [UN Comtrade API subscription keys](https://uncomtrade.org/docs/api-subscription-keys/)
- [UN Comtrade data-use policy](https://uncomtrade.org/docs/policy-on-comtrade-data-use/)
