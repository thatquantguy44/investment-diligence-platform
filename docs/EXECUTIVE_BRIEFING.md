# Investment Diligence Pipelines: Executive Briefing

## Summary

This repository is a **data-engineering foundation for investment diligence**. It pulls public, official data about companies, patents, research and trade. It stores the raw data unchanged, links records to the right company, checks quality, and publishes versioned datasets that downstream research tools can use.

It does **not** make investment decisions.

## Scope: US-first

The current build is **focused on the United States**. The core sources are US regulatory and government feeds:

| Source | Role | Coverage |
| --- | --- | --- |
| SEC EDGAR | Company identity and filings (Pipeline 01) | US |
| USPTO Open Data Portal | Patents (Pipeline 02) | US |
| GLEIF | Legal-entity identifiers (LEI) used to enrich entities | Global registry, used here for US watchlist entities |
| OpenAlex | Research-publication metadata (Pipeline 02) | International dataset, queried via its official API |
| UN Comtrade | Country and product trade flows (Pipeline 03) | International dataset, queried via its official API |

All sources are accessed through **official, documented APIs or bulk downloads** with the credentials and identification each provider requires. The watchlists and entity spine are US companies.

### Extending to other global sources

The pipeline pattern (capture, normalize, resolve, check, publish) is source-agnostic, so non-US sources can be added. Examples already in the specs are other national procurement portals, WIFO and CNIPA patent data, and multilingual news and documents.

**Non-US expansion needs more care than the US build.** Each new source must pass a source-policy review before any live connector is written:

- **No spoofing or evasion.** We do not disguise our identity, rotate IPs or fake browser fingerprints, and we do not bypass access controls or terms of service. Connectors send an honest, consistent User-Agent with contact information, use issued API keys, and respect rate limits and `Retry-After`.
- **Check access terms and licensing per source.** Some portals restrict automated access, reuse or redistribution. If no official or licensed feed exists, we do not build the connector.
- **Check legal and data-protection rules per jurisdiction.** This applies especially to personal data, such as inventors or hiring and career-page signals.
- **Handle language and schema differences.** Multilingual sources need translation and extraction with source-language excerpts and evidence spans preserved.
- **Review one country and one sector at a time.** This is already the roadmap rule for procurement signals.
- **Keep provenance.** Spoofing would also break the audit trail that makes the evidence defensible.

## How it works

```text
public source → immutable raw capture → normalized records → quality gates → published, versioned product
```

Design rules:

- **Audit trail.** Raw responses are append-only and addressed by content hash. Every derived record points back to its source.
- **No guessing.** Unknown dates stay null. Company matches are *suggestions* until a person reviews them.
- **Gated publishing.** If required quality checks fail, nothing is published.
- **Clean handoff.** A versioned data contract is the only interface to downstream systems (QuantSmith, the research-agent layer).
- **Storage.** Local files for development, PostgreSQL (database `IDP`) for real use.

## The pipelines

| # | Pipeline | Status | What it does |
| --- | --- | --- | --- |
| 01 | Entity graph | Pilot complete | SEC EDGAR watchlist plus optional GLEIF IDs. Builds the "who is who" spine. |
| 02 | Technology and talent | Pilot complete, hardening | OpenAlex research plus USPTO patents. Links inventors, institutions and topics. |
| 03 | Trade exposure | Pilot | UN Comtrade flows, concentration and mirror-trade discrepancies. |
| 04 | Public awards | Planned | Procurement and grant events. Needs one country and one sector chosen first. |
| 05 | Multilingual events | Planned | Document and event extraction. This is where LLMs come in. |

Spec 0002 (procurement and career-page signals) is planned. Spec 0003 (WIFO/CNIPA) is a placeholder with no scope yet.

## The ML integration

**Today there is no trained ML model in the pipelines.** What exists is deterministic code: exact-identifier entity matching, rule-based topic observations and statistical checks. Pipeline 02 is explicitly *not* an employment or technology-quality classifier.

**Designed but not yet built (Spec 0001):**

- **Local LLM interface.** A replaceable `ModelClient` protocol, running on local inference. The model, runtime and GPU platform are not yet chosen or approved.
- **Intended uses.** Translation and summarization, extraction of candidate events into a strict schema, and entity-linking assistance. Mainly for Pipeline 05.
- **Guardrails already specified:**
  - A model output is an *extracted claim*, not a verified fact.
  - Every claim carries its supporting text span.
  - Model ID, revision, prompt and schema version are logged.
  - Numbers and final feature calculations stay deterministic and code-owned.
  - Quality is measured against an analyst-reviewed evaluation set.
  - The model revision is pinned, with a rollback path.
- **Downstream ML and agents.** QuantSmith consumes the published datasets. That layer lives outside this repo by design.

**Framing:** we built the trustworthy, auditable data layer first. ML and LLMs plug in behind evidence and quality gates once the data is reliable.

## Open decisions

1. Which local LLM runtime and models are approved.
2. Which country and sector to use for procurement signals, which is also the first step of any non-US expansion.
3. Which scheduler and object store to use in production.
4. Which WIFO and CNIPA datasets matter, if any, and whether access terms allow our use.

## Where to look

- `README.md`: quick start
- `docs/MASTER_ROADMAP.md`: sequencing
- `docs/source-policy.md` and `docs/sources/`: per-source access rules
- `docs/specs/0001/`: full design, including the LLM boundary
