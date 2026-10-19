# GDELT DOC 2.0

## Purpose

Pipeline 05 uses the GDELT DOC 2.0 API for multilingual article discovery. It
supplies article URLs, titles, domains, languages, source countries, and the
time GDELT first saw each article.

## Access and credentials

No API key is required. The adapter sends one `mode=artlist&format=json`
request per run with at most 250 records (`--max-results`). Use `--timespan`
(for example `24h`, `7d`, `3m`) or `--start-datetime`/`--end-datetime` in
`YYYYMMDDHHMMSS`. `--source-language` and `--source-country` append GDELT's
`sourcelang:` and `sourcecountry:` operators to the query. Override the endpoint
with `GDELT_DOC_API_URL`.

GDELT asks clients to keep request rates low; the manifest budgets six requests
a minute and retries back off from five seconds.

## Response handling

- Malformed queries return a plain-text message instead of JSON; the adapter records it as `source_metadata.error` and blocks publication.
- An empty result (`{}`) is a warning, not an error.
- `seendate` (`YYYYMMDDTHHMMSSZ`) maps to `first_seen_at`; it is not the publisher's timestamp.

## Controls and limitations

- GDELT is a discovery index, not a complete archive or a source of truth.
- Only titles are used; follow-up fetching of article bodies or primary sources needs an allowlist and source review.
- `gdelt_doc_fixture` and `gdelt_artlist.json` are synthetic test inputs.

## Official references

- [GDELT DOC 2.0 API announcement and parameters](https://blog.gdeltproject.org/gdelt-doc-2-0-api-debuts/)
- [GDELT terms of use](https://www.gdeltproject.org/about.html#termsofuse)
