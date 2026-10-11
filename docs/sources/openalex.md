# OpenAlex

## Purpose

Pipeline 02 uses OpenAlex Works metadata as a supplemental research and talent signal. It collects works, authors, institutions, publication dates, work type, and citation counts. It does not collect or infer full-text employment evidence.

## Access and credentials

Basic OpenAlex API use works without an API key. For bounded use, set an identifying email so OpenAlex can associate the request with a client:

```yaml
OPENALEX_EMAIL: "you@example.com"
```

The current adapter sends this as the `mailto` query parameter. A free OpenAlex API key is available for larger workloads, but key-based authentication is not required by the current bounded adapter.

## Endpoint and request shape

```text
https://api.openalex.org/works?search=<query>&per-page=<1..200>&mailto=<optional-email>
```

The current Pipeline 02 CLI requires a query and bounds `--max-results` to 1–200. Requests have bounded retries for transport failures and HTTP 429/5xx responses. OpenAlex 429 responses are retried with longer exponential backoff; when the server sends `Retry-After`, the adapter honors either seconds or an HTTP date, capped at 60 seconds per retry.

## Run examples

Live OpenAlex plus local USPTO index:

```bash
PYTHONPATH=src python -m diligence_pipelines.cli run 02_technology_talent \
  --query "solid state battery" \
  --max-results 10
```

Fully offline replay:

```bash
PYTHONPATH=src python -m diligence_pipelines.cli run 02_technology_talent \
  --query "solid state battery" \
  --max-results 1 \
  --openalex-fixture tests/fixtures/openalex_works.json \
  --patent-fixture tests/fixtures/patents.json
```

## Controls and limitations

- Preserve the OpenAlex work ID as the stable source identifier.
- Retain the raw response, request parameters, retrieval time, adapter version, and content hash.
- Use the public snapshot or a source-approved local export when repeatability at scale is required.
- Research metadata is not evidence of employment, ownership, technical quality, or causality.
- `openalex_fixture` is synthetic and must not be displayed as live source evidence.

## Official references

- [OpenAlex API reference](https://help.openalex.org/api/)
- [OpenAlex authentication and rate limits](https://help.openalex.org/api/authentication/)
- [OpenAlex works endpoint](https://api.openalex.org/works)
