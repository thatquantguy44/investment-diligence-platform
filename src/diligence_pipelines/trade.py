from __future__ import annotations

from collections import defaultdict
from typing import Sequence


def _group_key(record: dict) -> tuple[str, str, str, str]:
    return (record["period"], record["reporter_code"], record["hs_code"], record["flow"])


def derive_trade_outputs(records: Sequence[dict]) -> dict[str, list[dict]]:
    exposure_groups: dict[tuple, list[dict]] = defaultdict(list)
    for record in records:
        exposure_groups[_group_key(record)].append(record)

    exposure = []
    concentration = []
    for group, rows in sorted(exposure_groups.items()):
        total = sum(row["trade_value_usd"] for row in rows)
        shares = []
        for row in rows:
            share = row["trade_value_usd"] / total if total else 0.0
            shares.append(share)
            exposure.append({
                "record_id": f"exposure:{'|'.join(group)}:{row['partner_code']}",
                "schema_version": "1.0.0",
                "pipeline_id": "03_trade_exposure",
                "period": row["period"], "reporter_code": row["reporter_code"], "reporter_name": row.get("reporter_name"),
                "hs_code": row["hs_code"], "flow": row["flow"], "partner_code": row["partner_code"], "partner_name": row.get("partner_name"),
                "trade_value_usd": row["trade_value_usd"], "partner_share": share, "total_group_value_usd": total,
                "source_record_id": row["source_record_id"],
            })
        top = max(rows, key=lambda row: row["trade_value_usd"]) if rows else None
        concentration.append({
            "record_id": f"concentration:{'|'.join(group)}",
            "schema_version": "1.0.0", "pipeline_id": "03_trade_exposure",
            "period": group[0], "reporter_code": group[1], "hs_code": group[2], "flow": group[3],
            "total_trade_value_usd": total, "partner_count": len(rows),
            "hhi": sum(share * share for share in shares) * 10000,
            "top_partner_code": top["partner_code"] if top else None,
            "top_partner_name": top.get("partner_name") if top else None,
            "top_partner_share": max(shares) if shares else 0.0,
            "formula_version": "partner_hhi.v1: sum(partner_share^2) * 10000",
            "source_record_ids": sorted({row["source_record_id"] for row in rows}),
        })

    by_direction: dict[tuple[str, str, str, str], dict[str, dict]] = defaultdict(dict)
    for record in records:
        flow = record["flow"]
        if "export" in flow or flow in {"x", "xout"}:
            direction = "export"
        elif "import" in flow or flow in {"m", "min"}:
            direction = "import"
        else:
            continue
        key = (record["period"], record["hs_code"], record["reporter_code"], record["partner_code"])
        by_direction[key][direction] = record

    discrepancies = []
    seen_pairs = set()
    for key, directions in by_direction.items():
        period, hs_code, reporter_code, partner_code = key
        counterpart_key = (period, hs_code, partner_code, reporter_code)
        export = directions.get("export") or by_direction.get(counterpart_key, {}).get("export")
        mirror_import = directions.get("import") or by_direction.get(counterpart_key, {}).get("import")
        if not export or not mirror_import:
            continue
        pair_key = tuple(sorted((key, counterpart_key)))
        if pair_key in seen_pairs:
            continue
        seen_pairs.add(pair_key)
        export_value = export["trade_value_usd"]
        mirror_value = mirror_import["trade_value_usd"]
        denominator = max(export_value, mirror_value)
        difference = export_value - mirror_value
        discrepancies.append({
            "record_id": f"mirror:{period}|{hs_code}|{min(reporter_code, partner_code)}|{max(reporter_code, partner_code)}",
            "schema_version": "1.0.0", "pipeline_id": "03_trade_exposure",
            "period": period, "hs_code": hs_code,
            "reporter_code": export["reporter_code"], "reporter_name": export.get("reporter_name"),
            "partner_code": export["partner_code"], "partner_name": export.get("partner_name"),
            "reported_export_value_usd": export_value, "mirror_import_value_usd": mirror_value,
            "difference_usd": difference,
            "discrepancy_ratio": abs(difference) / denominator if denominator else 0.0,
            "source_record_ids": [export["source_record_id"], mirror_import["source_record_id"]],
            "formula_version": "mirror_discrepancy.v1: abs(export - mirror_import) / max(export, mirror_import)",
        })
    return {"product_country_exposure": exposure, "partner_concentration": concentration, "mirror_trade_discrepancies": discrepancies}


def coverage_report(records: Sequence[dict], outputs: dict[str, list[dict]], configured_hs_codes: set[str] | None = None) -> dict:
    observed = {record["hs_code"] for record in records}
    configured = configured_hs_codes or observed
    missing = sorted(configured - observed)
    mirror_candidates = sum(1 for record in records if "export" in record["flow"] or "import" in record["flow"])
    return {
        "input_trade_flow_count": len(records),
        "observed_hs_codes": sorted(observed),
        "configured_hs_codes": sorted(configured),
        "missing_hs_codes": missing,
        "missingness_rate": len(missing) / len(configured) if configured else 0.0,
        "partner_concentration_groups": len(outputs["partner_concentration"]),
        "mirror_candidate_flow_count": mirror_candidates,
        "mirror_pair_count": len(outputs["mirror_trade_discrepancies"]),
        "limitations": ["Country/product aggregates do not establish named-company activity.", "Mirror differences can reflect timing, valuation, routing, re-exports, units, or reporting coverage."],
    }
