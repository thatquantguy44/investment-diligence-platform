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

Rule-based extraction (`event_rules.v1` in `src/diligence_pipelines/events.py`) are English
first, with a small set of Spanish, French, German, Chinese, and Japanese terms.
Documents with no candidate are counted in the coverage report; they are not
evidence that no event occurred.

## Extractors

`--extractor rules` (default) runs `RuleBasedEventExtractor`. `--extractor llm`
runs `LLMEventExtractor` against a local Ollama-compatible server
(`--llm-model` or `LLM_EVENT_MODEL`; `--llm-url` or `LLM_BASE_URL`, default
`http://localhost:11434`). Both implement the `EventExtractor` protocol and
produce the same candidate shape under the same gates. The manifest and every
candidate record `extractor_id`, `model_name`, `model_revision`,
`prompt_version`, and `schema_version`.

The LLM extractor is built so a model error cannot become a fact:

- The prompt (`event_extraction_prompt.v1`) asks for JSON with an allowed
  `event_type`, an `excerpt` copied from the headline, and a `confidence`.
- The model never supplies positions. The extractor finds the excerpt in the
  headline itself and stores the headline's own text and offsets, so the
  `event_evidence_supported` gate holds by construction.
- Output is rejected and counted (not published) when the excerpt is not in the
  headline, the event type is unknown, the item is malformed, or the response
  is not valid JSON. At most one candidate per headline and event type is kept.
- Requests use temperature 0 and a fixed seed. The model's digest is read from
  the server and recorded as `model_revision`; the run fails if the model is
  not installed.
- Headlines are untrusted: they are fenced in the prompt with an instruction to
  ignore embedded instructions, and the output checks above limit what an
  injected headline could do to a quote from itself in an allowed event type.
- Headlines are only sent to loopback hosts unless `--llm-allow-remote` is
  passed.
- Per-run `extractor_stats` (calls, failures, rejections by reason, accepted)
  go into the coverage report. The `event_extractor_health` gate warns when
  some calls fail and blocks publication when every call fails.

Candidates stay `candidate` regardless of extractor or confidence.

## Evaluating an extractor before trusting it

```bash
PYTHONPATH=src python -m diligence_pipelines.cli evaluate-event-extractor \
  --labels tests/fixtures/event_eval_seed.jsonl \
  --extractor llm --llm-model <model> --compare-rules --min-f1 0.85 \
  --output .data/eval/llm_vs_rules.json
```

Nothing is fetched or published. The report gives per-event-type and
per-language precision, recall, and F1, the mismatched headlines, and, with
`--compare-rules`, the headlines where the LLM and the rules disagree and the
micro-F1 change. `--min-f1` makes the command exit non-zero below a threshold,
so it can gate a model or prompt change.

**The bundled seed set is not a benchmark.** `tests/fixtures/event_eval_seed.jsonl`
has 24 synthetic headlines that the author wrote knowing the rules, so the
rules score about 0.95 on it; it only exercises the harness. It does show two
known rule weaknesses: a false positive on "merger wave" commentary and a miss
on French "lance". Before choosing between rules and a model, label a few
hundred real headlines pulled from GDELT in the same JSONL format
(`{"title", "language", "events": [...]}`), including headlines with no event.

**Not yet verified against a real model.** The extractor, client, and
evaluation are tested with a fake client and a fake Ollama HTTP server; no real
model has been run, and the sandbox had no local model server. Model quality,
latency, and cost per headline are unmeasured.

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

The live GDELT connector has been unit-tested against mocked responses but has
not yet been run against the real API from this repository. Add
`--extractor llm --llm-model <model>` to either command to use the local model.

## Quality gates

Publication is blocked when document or candidate IDs repeat, a candidate
references a missing document, an excerpt does not match its locator, extractor
identity is incomplete, a candidate is marked anything other than `candidate`,
or GDELT returns an error message instead of JSON.

## Controls and limitations

- GDELT is a discovery index, not a complete news archive or an authority on the truth of a claim.
- Candidates are extracted from headlines only; article bodies are not fetched.
- An LLM can paraphrase, over-read a headline, or miss events in low-resource languages; evaluate it on labeled real headlines first.
- Report time (GDELT first-seen) is not event time; event time stays null unless a source states it.
- Entity edges are exact name mentions and remain unreviewed; common names can produce false links.
