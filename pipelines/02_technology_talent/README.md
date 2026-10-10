# Pipeline 02 — Technology and talent signals

The initial slice uses OpenAlex research metadata to create evidence-backed `research_works` records. It is intentionally not an employment or technology-quality classifier. Patent adapters, inventor edges, institution edges, and deterministic topic aggregates are next.

Run a bounded search:

```bash
PYTHONPATH=src python -m diligence_pipelines.cli run 02_technology_talent \
  --query "solid state battery" \
  --max-results 10
```

Each output record retains the OpenAlex work ID, title, publication date, authors, institutions, citation count, source-record ID, and run ID. The raw OpenAlex response and product manifest are published to the configured backend.
