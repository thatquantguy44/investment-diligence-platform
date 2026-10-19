from __future__ import annotations

import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Sequence

import yaml

from diligence_pipelines.entities.matching import suggest_match


def load_award_sector(name: str, path: Path) -> dict:
    """Return one named sector preset from the award sectors YAML file."""
    sectors = (yaml.safe_load(path.read_text()) or {}).get("sectors") or {}
    if name not in sectors:
        raise ValueError(f"Unknown award sector {name!r}; choose from: {', '.join(sorted(sectors))}")
    sector = sectors[name]
    return {
        "name": name,
        "title": sector.get("title", name),
        "award_group": sector.get("award_group", "contracts"),
        "naics": [str(code) for code in sector.get("naics") or []],
        "psc": [str(code) for code in sector.get("psc") or []],
        "keywords": [str(word) for word in sector.get("keywords") or []],
    }


def _recipient_key(award: dict) -> str:
    if award.get("recipient_uei"):
        return f"uei:{award['recipient_uei']}"
    if award.get("recipient_hash"):
        return f"usaspending_recipient:{award['recipient_hash']}"
    name = re.sub(r"[^a-z0-9]", "", (award.get("recipient_name") or "").casefold())
    return f"name:{name or 'unknown'}"


def _quarter(date: str | None) -> str | None:
    if not date or len(date) < 7 or not date[:4].isdigit() or not date[5:7].isdigit():
        return None
    return f"{date[:4]}-Q{(int(date[5:7]) - 1) // 3 + 1}"


def derive_award_outputs(
    awards: Sequence[dict],
    events: Sequence[dict],
    *,
    entity_candidates: list[tuple[str, str]] | None = None,
    match_threshold: float = 0.70,
    window_start: str | None = None,
) -> dict[str, list[dict]]:
    by_recipient: dict[str, list[dict]] = defaultdict(list)
    for award in awards:
        by_recipient[_recipient_key(award)].append(award)
    award_by_id = {award["award_id"]: award for award in awards}
    events = [{**event, "is_deobligation": (event.get("federal_action_obligation_usd") or 0.0) < 0} for event in events]
    events_by_recipient: dict[str, list[dict]] = defaultdict(list)
    for event in events:
        if event["award_id"] in award_by_id:
            events_by_recipient[_recipient_key(award_by_id[event["award_id"]])].append(event)

    recipients = []
    for key, rows in sorted(by_recipient.items()):
        names = Counter(row.get("recipient_name") for row in rows if row.get("recipient_name"))
        name = names.most_common(1)[0][0] if names else None
        candidates = suggest_match(name, entity_candidates, match_threshold) if name and entity_candidates else []
        base_dates = [row["base_obligation_date"] for row in rows if row.get("base_obligation_date")]
        first_base = min(base_dates) if base_dates else None
        deobligations = [event for event in events_by_recipient[key] if event["is_deobligation"]]
        recipients.append({
            "record_id": f"recipient:{key}",
            "schema_version": "1.0.0",
            "pipeline_id": "04_public_awards",
            "recipient_key": key,
            "recipient_name": name,
            "name_variants": sorted(names),
            "recipient_uei": next((row["recipient_uei"] for row in rows if row.get("recipient_uei")), None),
            "recipient_hash": next((row["recipient_hash"] for row in rows if row.get("recipient_hash")), None),
            "award_count": len(rows),
            "total_obligated_usd": sum(row.get("obligated_amount_usd") or 0.0 for row in rows),
            "award_ids": sorted(row["award_id"] for row in rows),
            "first_base_obligation_date": first_base,
            # True when every award in this pull with a known base date started inside the window.
            # It is relative to this pull only, not to the recipient's full federal history.
            "new_entrant_in_window": (first_base >= window_start) if first_base and window_start else None,
            "deobligation_count": len(deobligations),
            "deobligated_usd": sum(event["federal_action_obligation_usd"] for event in deobligations),
            # Name similarity is an unreviewed lead only; it never confirms the recipient is a Pipeline 01 entity.
            "entity_match_candidates": [
                {"candidate_entity_id": item.candidate_entity_id, "match_method": item.method, "match_score": item.score, "review_status": item.review_status}
                for item in candidates
            ],
        })

    tags = []
    for award in awards:
        classifications = [("naics", award.get("naics_code"), award.get("naics_description")), ("psc", award.get("psc_code"), award.get("psc_description"))]
        classifications += [("assistance_listing", row["code"], row.get("description")) for row in award.get("assistance_listings") or []]
        for scheme, code, description in classifications:
            if not code:
                continue
            tags.append({
                "record_id": f"tag:{award['award_id']}:{scheme}:{code}",
                "schema_version": "1.0.0",
                "pipeline_id": "04_public_awards",
                "award_id": award["award_id"],
                "tag_scheme": scheme,
                "tag_code": code,
                "tag_description": description,
                "tag_method": "source_classification",
                "source_record_id": award["source_record_id"],
            })

    by_group: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for award in awards:
        by_group[(award["award_group"], award.get("naics_code") or award.get("psc_code") or "unclassified")].append(award)
    concentration = []
    for (award_group, classification), rows in sorted(by_group.items()):
        totals: dict[str, float] = defaultdict(float)
        for row in rows:
            totals[_recipient_key(row)] += row.get("obligated_amount_usd") or 0.0
        total = sum(totals.values())
        shares = {key: value / total for key, value in totals.items()} if total > 0 else {}
        top_key = max(shares, key=shares.get) if shares else None
        concentration.append({
            "record_id": f"recipient_concentration:{award_group}:{classification}",
            "schema_version": "1.0.0",
            "pipeline_id": "04_public_awards",
            "award_group": award_group,
            "classification_code": classification,
            "award_count": len(rows),
            "recipient_count": len(totals),
            "total_obligated_usd": total,
            "recipient_hhi": sum(share * share for share in shares.values()) * 10000 if shares else None,
            "top_recipient_key": top_key,
            "top_recipient_share": shares.get(top_key) if top_key else None,
            "formula_version": "recipient_hhi.v1: sum(recipient_obligation_share^2) * 10000",
            "award_ids": sorted(row["award_id"] for row in rows),
        })

    trend_groups: dict[tuple[str, str, str], list[dict]] = defaultdict(list)
    for event in events:
        award = award_by_id.get(event["award_id"])
        quarter = _quarter(event.get("action_date"))
        if not award or not quarter:
            continue
        trend_groups[("recipient", _recipient_key(award), quarter)].append(event)
        trend_groups[("classification", f"{award['award_group']}:{award.get('naics_code') or award.get('psc_code') or 'unclassified'}", quarter)].append(event)
    trends = []
    for (scope, scope_key, quarter), rows in sorted(trend_groups.items()):
        amounts = [row.get("federal_action_obligation_usd") or 0.0 for row in rows]
        trends.append({
            "record_id": f"obligation_trend:{scope}:{scope_key}:{quarter}",
            "schema_version": "1.0.0",
            "pipeline_id": "04_public_awards",
            "scope": scope,
            "scope_key": scope_key,
            "quarter": quarter,
            "action_count": len(rows),
            "net_obligation_usd": sum(amounts),
            "deobligation_usd": sum(amount for amount in amounts if amount < 0),
            "award_ids": sorted({row["award_id"] for row in rows}),
            "formula_version": "obligation_trend.v1: sum(federal_action_obligation) by action-date calendar quarter",
        })

    return {
        "award_events": events,
        "recipient_entities": recipients,
        "technology_program_tags": tags,
        "recipient_concentration": concentration,
        "obligation_trends": trends,
    }


def award_coverage_report(awards: Sequence[dict], events: Sequence[dict], source_metadata: dict, transaction_award_ids: set[str]) -> dict:
    award_ids = {award["award_id"] for award in awards}
    modification_keys = Counter((event["award_id"], event.get("modification_number")) for event in events if event.get("modification_number"))
    return {
        "input_award_count": len(awards),
        "award_event_count": len(events),
        "awards_with_transaction_history": len(award_ids & transaction_award_ids),
        "awards_without_transaction_history": sorted(award_ids - transaction_award_ids),
        "missing_recipient_uei_count": sum(not award.get("recipient_uei") for award in awards),
        "missing_obligation_amount_count": sum(award.get("obligated_amount_usd") is None for award in awards),
        "missing_base_obligation_date_count": sum(not award.get("base_obligation_date") for award in awards),
        "duplicate_modification_numbers": sorted(f"{award_id}:{mod}" for (award_id, mod), count in modification_keys.items() if count > 1),
        "result_truncated": bool(source_metadata.get("truncated")),
        "limitations": [
            "An award or obligation is not evidence of contract performance, payment, revenue, or product-market fit.",
            "Obligated amounts are commitments; outlays are disbursements. Neither is an announced amount.",
            "Recipient-to-entity matches are unreviewed name-similarity candidates.",
            "Obligation trends cover only awards whose transaction history was fetched; new-entrant flags are relative to this pull.",
        ],
    }
