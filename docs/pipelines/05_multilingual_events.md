# Pipeline 05 — Multilingual company and policy event stream

The prototype discovers articles through the GDELT DOC 2.0 API, normalizes
headline-level source documents, and extracts event candidates with a
deterministic rule-based extractor. Every candidate carries an exact evidence
span (`title[start:end]`) that quality gates check against the source text.
Candidates are never promoted to verified events by this pipeline.

See the [GDELT source runbook](../sources/gdelt.md) for access, rate limits,
and query syntax.

## Outputs

| Output | Grain | Notes |
| --- | --- | --- |
| `source_documents` | One row per canonical URL | URL canonicalized (scheme/host case, `www.`, tracking parameters); `first_seen_at` is GDELT's seen time; `published_at` stays null; syndicated copies (same normalized title) point at the earliest copy via `duplicate_of` |
| `event_candidates` | One row per original document × event type | Event type, evidence locator and excerpt, `report_time`, null `event_time`, `status: candidate`, extractor identity |
| `entity_event_edges` | One row per entity mention × candidate | Exact, word-bounded name mention (legal suffixes stripped); `review_status: unreviewed` |
| `event_signal_counts` | One row per entity (or `unmatched`) × event type × report date | Candidate count and distinct reporting domains, including syndicated copies |

`verified_events` from the Spec 0001 output list is deliberately not
published: verification needs analyst review or primary-source confirmation.

## Event types

`funding_round`, `acquisition`, `partnership`, `facility`,
`workforce_reduction`, `regulatory_action`, `government_award`,
`product_launch`, `leadership_change`, `legal_dispute`, `insolvency`.

Rules (`event_rules.v1` in `src/diligence_pipelines/events.py`) are English
first, with a small set of Spanish, French, German, Chinese, and Japanese terms.
Documents with no candidate are counted in the coverage report; they are not
evidence that no event occurred.

## Extractor contract and the LLM step

`RuleBasedEventExtractor` is the reference implementation of the
`EventExtractor` protocol. The product manifest and every candidate record the
extractor's `extractor_id`, `model_name`, `model_revision`, `prompt_version`,
and `schema_version`. A local LLM extractor can replace it by returning the
same candidate shape; the `event_evidence_supported` gate rejects any excerpt
that does not match the source text at its locator. An LLM extractor is not yet
implemented.

## Offline fixture replay

```bash
PYTHONPATH=src python -m diligence_pipelines.cli run 05_multilingual_events \
  --events-fixture tests/fixtures/gdelt_artlist.json \
  --entities tests/fixtures/entity_graph.jsonl
```

The fixture is synthetic. Use `DILIGENCE_STORAGE_BACKEND=postgres` to publish to
`diligence.source_documents`, `diligence.event_candidates`,
`diligence.entity_event_edges`, and `diligence.event_signal_counts`.

## Sector presets and award recipients

`--sector <name>` loads a GDELT query from
[`config/event_queries.yaml`](../../config/event_queries.yaml). The five
presets mirror the Pipeline 04 defense and technology sectors; `--query` adds
an extra AND term (for example a company name).

`--entities` accepts either a Pipeline 01 `entities.jsonl` or a Pipeline 04
`recipient_entities.jsonl`. With recipients, edges point at the recipient key
(`uei:...`), which shows award recipients appearing in funding, acquisition, or
regulatory headlines. Those edges are unreviewed name mentions.

```bash
PYTHONPATH=src python -m diligence_pipelines.cli run 05_multilingual_events \
  --sector defense_electronics_sensing --timespan 30d \
  --entities .data/curated/04_public_awards/<run_id>/recipient_entities.jsonl
```

## Non-publishing validation and live path

```bash
PYTHONPATH=src python -m diligence_pipelines.cli validate-gdelt \
  --query '"silicon carbide"' --timespan 7d --max-results 75

PYTHONPATH=src python -m diligence_pipelines.cli run 05_multilingual_events \
  --query '"silicon carbide"' --timespan 7d --source-language english \
  --entities .data/curated/01_entity_graph/<run_id>/entities.jsonl
```

The live connector has been unit-tested against mocked responses but has not
yet been run against the real API from this repository.

## Quality gates

Publication is blocked when document or candidate IDs repeat, a candidate
references a missing document, an excerpt does not match its locator, extractor
identity is incomplete, a candidate is marked anything other than `candidate`,
or GDELT returns an error message instead of JSON.

## Controls and limitations

- GDELT is a discovery index, not a complete news archive or an authority on the truth of a claim.
- Candidates are extracted from headlines only; article bodies are not fetched.
- Report time (GDELT first-seen) is not event time; event time stays null unless a source states it.
- Entity edges are exact name mentions and remain unreviewed; common names can produce false links.
