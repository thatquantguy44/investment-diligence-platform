# FundComb manual investor-map pilot

This is an offline research workflow for an analyst-curated sample of public
[FundComb investor profiles](https://www.fundcomb.com/search). It is not a
FundComb API adapter, website crawler, complete investor database, or curated
production product. The command makes **no network requests**. The source's
[Data API](https://www.fundcomb.com/developers) remains a separate, entitled
path whose access and rights require review.

## Input

Create a CSV under the ignored `.data/` directory, for example
`.data/fundcomb/manual_profiles.csv`. Keep sourced records out of Git. Each row
is one investor-profile claim about one focus area:

| Column | Meaning |
| --- | --- |
| `investor_name` | Name displayed on the profile |
| `profile_url` | HTTPS `fundcomb.com/funds/<slug>` source URL |
| `headquarters_country` | Profile's stated HQ country, or `Unknown` |
| `focus_area` | `semiconductors`, `sensors`, or `maritime_systems` |
| `evidence_excerpt` | Short excerpt copied from the **target profile**, not its similar-investor/sidebar content |
| `evidence_kind` | `profile_focus` or `profile_description` |
| `observed_on` | Analyst's UTC observation date, `YYYY-MM-DD` |

Include only a focus-area row when the target profile itself gives specific
evidence for it. A company name appearing in a sidebar is not evidence about
the target investor. Preserve conflicting or uncertain claims as review notes
outside this CSV; never silently resolve them. This pilot intentionally omits
person/contact information, round amounts, and supply-chain relationships.

## Run

```bash
PYTHONPATH=src python -m diligence_pipelines.cli map-fundcomb-csv \
  --input .data/fundcomb/manual_profiles.csv \
  --output-dir .data/fundcomb/map
```

The output contains `investor_focus_observations.jsonl` and
`sample_report.json`, including an input SHA-256 and counts by focus area.
Rows are unreviewed `profile_claim` observations. A zero count means no
curated rows in this sample, never zero investors or market activity.

## Current pilot result and next gate

On 2026-11-17, six manually reviewed public profiles yielded six
semiconductor-related observations, none for sensors or maritime systems.
The sample is skewed toward South Korean profiles, with one India-based and one
HQ-unreported profile; it cannot estimate Southeast Asian investor coverage or
capital flow. The exact locally curated CSV and output remain under ignored
`.data/`. The publicly visible FundComb searches for `sensor` and `maritime`
did not yield clear profile results during this small pilot; this is a search
and sample limitation, not evidence of no activity.

Before any scheduled or broad collection, complete the source-policy review:
permitted acquisition method, terms, retention, attribution, rate limit, and
rights for downstream use. The manual workflow can be rerun on an approved
operator-supplied CSV without changing the adapter.
