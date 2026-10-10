from __future__ import annotations

from collections import Counter

from diligence_pipelines.contracts import Entity, QualityResult


def validate_entities(records: list[Entity]) -> list[QualityResult]:
    ids = [record.entity_id for record in records]
    duplicate_count = sum(count - 1 for count in Counter(ids).values() if count > 1)
    missing_source_refs = sum(not record.source_id or not record.run_id for record in records)
    return [
        QualityResult(check_id="schema_valid", status="pass", observed_value=len(records)),
        QualityResult(
            check_id="identifier_unique",
            status="fail" if duplicate_count else "pass",
            observed_value=duplicate_count,
            threshold=0,
            details="Duplicate entity IDs" if duplicate_count else None,
        ),
        QualityResult(
            check_id="source_ref_present",
            status="fail" if missing_source_refs else "pass",
            observed_value=missing_source_refs,
            threshold=0,
            details="Records missing source or run references" if missing_source_refs else None,
        ),
    ]


def validate_research_works(records: list[dict]) -> list[QualityResult]:
    work_ids = [record.get("work_id") for record in records]
    duplicate_count = len(work_ids) - len(set(work_ids))
    missing_source_refs = sum(not record.get("source_record_id") for record in records)
    return [
        QualityResult(check_id="schema_valid", status="pass", observed_value=len(records)),
        QualityResult(check_id="identifier_unique", status="fail" if duplicate_count else "pass", observed_value=duplicate_count, threshold=0),
        QualityResult(check_id="source_ref_present", status="fail" if missing_source_refs else "pass", observed_value=missing_source_refs, threshold=0),
    ]
