# USAspending

## Purpose

Pipeline 04 uses USAspending as the reference implementation for public awards:
federal contracts and financial-assistance awards (grants), with their
transaction-level modification history.

## Access and credentials

No API key is required. The adapter calls:

- `POST /api/v2/search/spending_by_award/`: award search, at most 100 rows per page; the adapter pages until `--max-results` or `hasNext: false`.
- `POST /api/v2/transactions/`: transaction history for one award, keyed by `generated_internal_id`.

Both URLs can be overridden with `USASPENDING_AWARD_SEARCH_URL` and
`USASPENDING_TRANSACTIONS_URL`. Keep pulls bounded: one date window, one sector
filter, and a small `--max-transaction-awards`, since each one costs one request.

## Field semantics

- `Award Amount` → `obligated_amount_usd` (total obligation, which can fall after de-obligation).
- `Total Outlays` → `outlay_amount_usd` (disbursed; often null for recent awards).
- `announced_amount_usd` stays null; USAspending does not publish announcements.
- `Base Obligation Date`, `Start Date`, `End Date`, and `Last Modified Date` are kept as separate fields.
- NAICS and PSC can arrive as a code string or as `{code, description}`; both are accepted.
- Contracts use award type codes `A`–`D`; grants use `02`–`05`.

## Controls and limitations

- Award records reflect current state; amendment history comes from transactions.
- Recipient names vary between awards; group by UEI where present.
- `usaspending_fixture` and `usaspending_awards.json` are synthetic test inputs.
- Confirm the current API terms and any rate guidance before scheduled use.

## Official references

- [USAspending API documentation](https://api.usaspending.gov/docs/)
- [Award search endpoint](https://github.com/fedspendingtransparency/usaspending-api/blob/master/usaspending_api/api_contracts/contracts/v2/search/spending_by_award.md)
- [Transactions endpoint](https://github.com/fedspendingtransparency/usaspending-api/blob/master/usaspending_api/api_contracts/contracts/v2/transactions.md)
- [USAspending data dictionary](https://www.usaspending.gov/data-dictionary)
