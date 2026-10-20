from __future__ import annotations

from collections import defaultdict
from datetime import date
from typing import Sequence

ANNUAL_MIN_DAYS = 350
ANNUAL_MAX_DAYS = 380
# Order matters for revenue: the first alias with annual data for a period wins.
REVENUE_ALIASES = ("Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax", "SalesRevenueNet")
FORMULA_VERSION = "financial_metrics.v1: latest-filed annual (350-380 day, USD) value per concept and period end; ratios are null when the denominator is missing or not positive"


def _ratio(numerator: float | None, denominator: float | None) -> float | None:
    if numerator is None or denominator is None or denominator <= 0:
        return None
    return numerator / denominator


def _is_annual(fact: dict) -> bool:
    return fact["duration_days"] is not None and ANNUAL_MIN_DAYS <= fact["duration_days"] <= ANNUAL_MAX_DAYS


def _latest_by_period(facts: Sequence[dict]) -> dict[tuple[str, str], dict]:
    """Pick the most recently filed observation per (concept, period end), noting restatements."""
    grouped: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for fact in facts:
        grouped[(fact["concept"], fact["period_end"])].append(fact)
    picked = {}
    for key, rows in grouped.items():
        latest = max(rows, key=lambda row: (row["filed_at"] or "", row["accession_number"]))
        picked[key] = {**latest, "restated": len({row["value"] for row in rows}) > 1, "observation_count": len(rows)}
    return picked


def derive_financial_metrics(facts: Sequence[dict]) -> list[dict]:
    """Build one annual metrics row per company and fiscal period end."""
    by_company: dict[str, list[dict]] = defaultdict(list)
    for fact in facts:
        by_company[fact["cik"]].append(fact)

    metrics = []
    for cik, company_facts in sorted(by_company.items()):
        annual = _latest_by_period([fact for fact in company_facts if _is_annual(fact)])
        instants = _latest_by_period([fact for fact in company_facts if fact["period_start"] is None])
        period_ends = sorted({period_end for (_, period_end) in annual} | {period_end for (_, period_end) in instants})
        rows_by_end: dict[str, dict] = {}
        for period_end in period_ends:
            used: list[dict] = []

            def pick(concepts: Sequence[str], source: dict = annual) -> dict | None:
                for concept in concepts:
                    found = source.get((concept, period_end))
                    if found:
                        used.append(found)
                        return found
                return None

            revenue = pick(REVENUE_ALIASES)
            rd = pick(("ResearchAndDevelopmentExpense",))
            capex = pick(("PaymentsToAcquirePropertyPlantAndEquipment",))
            net_income = pick(("NetIncomeLoss",))
            operating_income = pick(("OperatingIncomeLoss",))
            assets = pick(("Assets",), instants)
            if not used:
                continue
            value = lambda found: found["value"] if found else None  # noqa: E731
            row = {
                "record_id": f"financial_metric:sec:{cik}:{period_end}",
                "schema_version": "1.0.0",
                "pipeline_id": "01_entity_graph",
                "entity_id": f"entity:sec:{cik}",
                "cik": cik,
                "period_end": period_end,
                "revenue_usd": value(revenue),
                "revenue_concept": revenue["concept"] if revenue else None,
                "rd_expense_usd": value(rd),
                "capex_usd": value(capex),
                "net_income_usd": value(net_income),
                "operating_income_usd": value(operating_income),
                "total_assets_usd": value(assets),
                "rd_intensity": _ratio(value(rd), value(revenue)),
                "capex_intensity": _ratio(value(capex), value(revenue)),
                "operating_margin": (value(operating_income) / value(revenue)) if revenue and operating_income and value(revenue) > 0 else None,
                "revenue_growth_yoy": None,
                # Latest filing date among the inputs: the figures were not public before this date.
                "as_of_filed": max(found["filed_at"] or "" for found in used) or None,
                "restated": any(found["restated"] for found in used),
                "input_fact_ids": sorted(found["fact_id"] for found in used),
                "formula_version": FORMULA_VERSION,
            }
            rows_by_end[period_end] = row

        ends = sorted(rows_by_end)
        for index, period_end in enumerate(ends):
            current = rows_by_end[period_end]
            for prior_end in reversed(ends[:index]):
                gap = (date.fromisoformat(period_end) - date.fromisoformat(prior_end)).days
                if ANNUAL_MIN_DAYS <= gap <= ANNUAL_MAX_DAYS:
                    current["revenue_growth_yoy"] = (
                        current["revenue_usd"] / rows_by_end[prior_end]["revenue_usd"] - 1
                        if current["revenue_usd"] is not None and (rows_by_end[prior_end]["revenue_usd"] or 0) > 0 else None
                    )
                    break
        metrics.extend(rows_by_end[period_end] for period_end in ends)
    return metrics


def financial_coverage_report(facts: Sequence[dict], metrics: Sequence[dict], metadata_by_cik: dict[str, dict], requested_ciks: Sequence[str]) -> dict:
    expected_groups = ("revenue", "rd_expense", "capex", "net_income", "operating_income", "total_assets")
    groups_by_cik: dict[str, set[str]] = defaultdict(set)
    for fact in facts:
        groups_by_cik[fact["cik"]].add(fact["concept_group"])
    latest_by_cik = {}
    for metric in metrics:
        latest_by_cik[metric["cik"]] = max(latest_by_cik.get(metric["cik"], ""), metric["period_end"])
    return {
        "requested_ciks": list(requested_ciks),
        "ciks_without_facts": sorted(set(requested_ciks) - {fact["cik"] for fact in facts}),
        "fact_count": len(facts),
        "metric_period_count": len(metrics),
        "missing_concept_groups_by_cik": {cik: sorted(set(expected_groups) - groups_by_cik.get(cik, set())) for cik in requested_ciks},
        "latest_period_end_by_cik": latest_by_cik,
        "restated_period_count": sum(bool(metric["restated"]) for metric in metrics),
        "entity_names": {cik: metadata.get("entity_name") for cik, metadata in metadata_by_cik.items()},
        "limitations": [
            "Facts cover a bounded concept set from annual forms (10-K/20-F/40-F) in USD only; quarterly data and other concepts are not collected.",
            "Companies tag the same item differently; a missing concept group may be tagged under a concept outside this set.",
            "Values are as reported by the filer in XBRL and are not adjusted for restatements, acquisitions, or accounting-standard changes.",
            "Derived ratios are descriptive and use latest-filed values; use as_of_filed for point-in-time analysis.",
        ],
    }
