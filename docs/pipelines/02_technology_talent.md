# Pipeline 02 — Technology and talent signals

The pilot combines OpenAlex research metadata with a USPTO/PatentsView patent response to create `research_works`, `patent_records`, `patent_assignments`, `inventor_edges`, `institution_edges`, and deterministic `technology_topic_observations`. It is intentionally not an employment or technology-quality classifier.

Run a bounded search:

```bash
PYTHONPATH=src python -m diligence_pipelines.cli run 02_technology_talent \
  --query "solid state battery" \
  --max-results 10
```

Live patent collection requires `USPTO_API_KEY` in `config/variables.yaml` or the environment. For an offline end-to-end test, use the checked-in synthetic response:

```bash
PYTHONPATH=src python -m diligence_pipelines.cli run 02_technology_talent \
  --query "solid state battery" \
  --max-results 1 \
  --patent-fixture tests/fixtures/patents.json
```

Each output record retains source identifiers, dates, authors/inventors, institutions/assignees, source-record IDs, and run IDs. Patent and research records remain source evidence; inventor and institution edges do not establish employment by a target company. Raw responses and the product manifest are published to the configured backend.
