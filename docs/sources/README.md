# Source setup and operating notes

These documents describe the external sources currently used or planned for the implemented pipelines. They are the setup and operating companion to the pipeline-specific documentation under [`docs/pipelines/`](../pipelines/).

| Source | Source ID(s) | Pipeline | Credentials |
| --- | --- | --- | --- |
| [SEC EDGAR](sec_edgar.md) | `sec_edgar` | 01 | No key; identifying `SEC_USER_AGENT` required |
| [GLEIF LEI API](gleif.md) | `gleif` | 01, optional enrichment | No key in the current adapter |
| [OpenAlex](openalex.md) | `openalex` | 02 | No key for bounded use; optional email/key for larger use |
| [USPTO ODP / PatentsView](uspto_odp.md) | `uspto_patents`, `uspto_patents_index` | 02 | ODP catalog access requires `USPTO_API_KEY`; local index queries do not |
| [UN Comtrade](un_comtrade.md) | `un_comtrade` | 03 | No key for preview; key recommended/required for broader API access |
| [USAspending](usaspending.md) | `usaspending`, `usaspending_transactions` | 04 | No key |
| [GDELT DOC 2.0](gdelt.md) | `gdelt_doc` | 05 | No key; keep request volume low |

## Shared credential setup

Keep local values in the ignored file:

```bash
cp config/variables_example.yaml config/variables.yaml
```

Never commit `config/variables.yaml`, API keys, passwords, or downloaded source artifacts. Environment variables override YAML values. The current example includes settings for all seven sources.

## Evidence boundary

Every successful source capture should preserve the source ID, request URI, sanitized parameters, retrieval time, status code, adapter version, content hash, and raw payload location. Fixture source IDs such as `synthetic_fixture`, `openalex_fixture`, `uspto_patents_fixture`, `un_comtrade_fixture`, `usaspending_fixture`, and `gdelt_doc_fixture` are synthetic test inputs and must not be treated as live evidence.
