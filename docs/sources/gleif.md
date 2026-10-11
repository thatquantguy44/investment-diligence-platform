# GLEIF LEI API

## Purpose

Pipeline 01 optionally enriches a SEC entity with a Legal Entity Identifier (LEI). A supplied LEI is validated locally, fetched from GLEIF, and normalized into an exact-identifier alias. Name similarity is not used as a confirmed match.

## Access and credentials

The current single-record GLEIF API path does not require an API key:

```text
https://api.gleif.org/api/v1/lei-records/{LEI}
```

Configure no credential for the current adapter. The API response is public LEI reference data; still preserve the retrieval metadata and source hash.

## Run example

Use a watchlist entry containing both a CIK and a 20-character LEI:

```yaml
entities:
  - cik: "320193"
    lei: "5493001KJTIIGC8Y1R12"
```

```bash
PYTHONPATH=src python -m diligence_pipelines.cli run 01_entity_graph \
  --watchlist config/watchlist_example.yaml
```

The LEI is validated before any network request. The resulting alias records `match_method: lei_exact`, `match_score: 1.0`, and `review_status: accepted`.

## Controls and limitations

- Retries are bounded for transport failures and HTTP 429/5xx responses.
- Treat unexpected JSON fields as schema drift; the adapter should ignore additive fields but fail safely on missing required identity fields.
- An exact LEI alias confirms the identifier-to-record relationship; it does not by itself establish control, ownership, or current operating status.
- Parent/child relationships are not currently materialized into the active Pipeline 01 product.

## Official references

- [GLEIF API](https://www.gleif.org/en/lei-data/gleif-api/)
- [GLEIF API supporting documents and changes](https://www.gleif.org/en/lei-data/gleif-api/)
