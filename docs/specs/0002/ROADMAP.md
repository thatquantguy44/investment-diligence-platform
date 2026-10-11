# Spec 0002 Roadmap

This roadmap covers public procurement/grant notices and company career-page
signals. Cross-spec sequencing lives in the repository
[MASTER_ROADMAP.md](../../MASTER_ROADMAP.md).

## Status

Spec 0002 is drafted but not yet implemented. Both slices remain bounded pilots;
neither should begin broad collection until its source boundary is approved.

## Procurement and grant notices

### Prerequisites

- Select one country.
- Select one sector and document its classification rules and synonyms.
- Identify official procurement, grant, ministry, agency, or public-finance
  portals.
- Complete source terms, access, rate-limit, language, and retention review.

### Build sequence

1. Add source adapters and permitted original-page/document capture.
2. Normalize notice, buyer, awardee, amount, currency, dates, project, location,
   status, and amendment relationships.
3. Preserve original-language text plus field-level evidence locators.
4. Generate unresolved awardee/entity match candidates against Pipeline 01.
5. Publish coverage, missingness, revision, and inaccessible-page metrics.

### Deferred expansion

- Additional countries, sectors, portals, and languages.
- Automated entity confirmation without analyst review.
- Treating notices as proof of contract performance, payment, revenue, or
  commercial success.

## Company career pages

### Prerequisites

- Define an approved company and domain allowlist.
- Confirm collection is permitted by page terms and access conditions.
- Define rate limits, caching, observation frequency, and retention rules.

### Build sequence

1. Capture permitted job-page evidence and stable source identifiers.
2. Normalize title, function, location, employment type, seniority, and dates.
3. Deduplicate syndicated or repeated postings.
4. Track observed active, stale, removed, and reactivated postings.
5. Publish role counts and changes by company, function, location, and date.

### Deferred expansion

- Broad job-board coverage beyond the approved allowlist.
- Treating posting counts as employee counts, confirmed hires, or certain
  expansion plans.
- Automated claims about hiring intent without analyst review and source
  evidence.
