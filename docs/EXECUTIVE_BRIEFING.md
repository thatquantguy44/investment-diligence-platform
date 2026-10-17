# Investment Diligence Pipelines: Overview

## The short version

This project is the data foundation for our investment diligence work. It pulls public, official data on companies, patents, research and trade. It keeps the raw data exactly as received, ties records to the right company, checks quality, and publishes versioned datasets that our research tools can build on.

It doesn't make investment decisions. It makes sure the data going into them is clean and traceable.

## Scope: US first

Right now I've kept this focused on the US. The core sources are US regulatory and government feeds:

| Source | What I use it for | Coverage |
| --- | --- | --- |
| SEC EDGAR | Company identity and filings (Pipeline 01) | US |
| USPTO Open Data Portal | Patents (Pipeline 02) | US |
| GLEIF | Legal-entity identifiers that enrich the entity records | Global registry, used here for US watchlist companies |
| OpenAlex | Research-publication metadata (Pipeline 02) | International dataset, reached through its official API |
| UN Comtrade | Country and product trade flows (Pipeline 03) | International dataset, reached through its official API |

Everything comes through official APIs or bulk downloads, using the keys and identification each provider asks for. The watchlists and the entity backbone are US companies.

### Going global

The design isn't tied to the US. Every pipeline follows the same steps (capture, normalize, resolve, check, publish), so adding other countries' sources is possible. The specs already point at other national procurement portals, WIFO and CNIPA patent data, and multilingual news and documents.

I would be more careful with non-US sources, though. Before I write any connector for one, I want it to pass a source-policy review:

- **No spoofing or evasion.** I won't disguise who we are, rotate IPs, fake browser fingerprints, or get around access controls or terms of service. Our connectors send an honest User-Agent with contact info, use issued API keys, and respect rate limits. That matters more abroad, where the rules and enforcement are less familiar to us.
- **Check the access terms and licensing for each source.** Some portals restrict automated access or reuse. If there's no official or licensed feed, I don't build the connector.
- **Check legal and data-protection rules for each country.** This is especially true for personal data, like inventors or career-page hiring signals.
- **Plan for language and format differences.** Multilingual sources need translation and extraction that keeps the original text and evidence.
- **Go one country and one sector at a time.** That's already the rule in the roadmap for procurement signals.
- **Keep the audit trail intact.** Spoofing would also undermine the provenance that makes this evidence defensible.

## How it works

```text
public source → immutable raw capture → normalized records → quality gates → published, versioned product
```

The rules I built it around:

- **Audit trail.** Raw responses are append-only and addressed by content hash. Every derived record points back to its source.
- **No guessing.** Unknown dates stay empty. Company matches are suggestions until a person reviews them.
- **Gated publishing.** If a required quality check fails, nothing gets published.
- **Clean handoff.** A versioned data contract is the only interface to downstream systems like QuantSmith, our research-agent layer.
- **Storage.** Local files for development and PostgreSQL (database `IDP`) for real use.

## The pipelines

| # | Pipeline | Status | What it does |
| --- | --- | --- | --- |
| 01 | Entity graph | Pilot complete | SEC EDGAR watchlist plus optional GLEIF IDs. This is the "who is who" backbone. |
| 02 | Technology and talent | Pilot complete, hardening | OpenAlex research plus USPTO patents. Links inventors, institutions and topics. |
| 03 | Trade exposure | Pilot | UN Comtrade flows, concentration and mirror-trade discrepancies. |
| 04 | Public awards | Planned | Procurement and grant events. Needs one country and one sector chosen first. |
| 05 | Multilingual events | Planned | Document and event extraction. This is where LLMs come in. |

Two specs sit behind the planned work. Spec 0002 covers procurement and career-page signals and is planned. Spec 0003 covers WIFO/CNIPA and is only a placeholder with no scope yet.

## Where ML fits

Today there is no trained ML model in these pipelines. What's there is deterministic code: exact-identifier entity matching, rule-based topic observations and statistical checks. Pipeline 02 is explicitly not an employment or technology-quality classifier.

What's designed but not built yet (Spec 0001):

- **A local LLM interface.** A replaceable `ModelClient` running on local inference. We haven't picked or approved the model, runtime or GPU platform.
- **What it's for.** Translation and summarization, pulling candidate events into a strict schema, and helping with entity linking. Mostly Pipeline 05.
- **The guardrails, already specified:**
  - A model output is an extracted claim, not a verified fact.
  - Every claim carries the text it came from.
  - Model ID, revision, prompt and schema version are logged.
  - Numbers and final feature calculations stay in deterministic code.
  - Quality is measured against an analyst-reviewed evaluation set.
  - The model revision is pinned, with a rollback path.
- **Downstream ML and agents.** QuantSmith consumes the published datasets. That layer lives outside this repo on purpose.

My thinking: build the trustworthy, auditable data layer first, then plug ML and LLMs in behind evidence and quality gates once the data is reliable.

## Decisions I need

1. Which local LLM runtime and models are approved.
2. Which country and sector to start with for procurement signals. This is also the first step of any non-US expansion.
3. Which scheduler and object store to use in production.
4. Which WIFO and CNIPA datasets matter, if any, and whether their access terms allow our use.

## Where to look

- `README.md`: quick start
- `docs/MASTER_ROADMAP.md`: sequencing
- `docs/source-policy.md` and `docs/sources/`: per-source access rules
- `docs/specs/0001/`: the full design, including the LLM boundary
