# SEC EDGAR

## Purpose

Pipeline 01 uses the SEC submissions API to resolve a company CIK into a source-backed entity record. The current bounded adapter fetches one company-submissions JSON document per CIK; it does not crawl filings.

## Access and credentials

The SEC data APIs do not require an API key. Automated requests must include an identifying User-Agent with a contact address. The SEC currently publishes a 10-requests-per-second fair-access limit; this project uses a lower manifest target of 8 requests per minute for the watchlist path.

Configure:

```yaml
SEC_USER_AGENT: "investment-diligence-pipelines/0.1 you@example.com"
```

The value can also be supplied as an environment variable. Do not use a generic or blank User-Agent.

## Endpoint and request shape

Current endpoint:

```text
https://data.sec.gov/submissions/CIK##########.json
```

The CIK must be normalized to ten digits with leading zeroes. Pipeline 01 validates CIK syntax before making a request, preserves the raw JSON response, and extracts the company name, jurisdiction, CIK, tickers, and exchanges.

## Run examples

Live single-company run:

```bash
SEC_USER_AGENT='investment-diligence-pipelines/0.1 you@example.com' \
PYTHONPATH=src python -m diligence_pipelines.cli run 01_entity_graph --cik 320193
```

Offline deterministic replay:

```bash
PYTHONPATH=src python -m diligence_pipelines.cli run 01_entity_graph \
  --input tests/fixtures/entity_graph.jsonl
```

## Controls and limitations

- Retries are bounded and apply to transport errors and HTTP 429/5xx responses.
- Raw captures are content-addressed and are not overwritten on rerun.
- SEC CIK identity is source evidence, not a complete ownership graph.
- The current adapter does not fetch filing contents or infer beneficial ownership.

## Official references

- [SEC EDGAR APIs](https://www.sec.gov/search-filings/edgar-application-programming-interfaces)
- [SEC accessing EDGAR data](https://www.sec.gov/search-filings/edgar-search-assistance/accessing-edgar-data)
- [SEC developer resources and fair access](https://www.sec.gov/about/developer-resources)
