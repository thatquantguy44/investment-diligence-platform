from __future__ import annotations

from collections import Counter

from diligence_pipelines.contracts import Entity, QualityResult


def validate_entities(records: list[Entity]) -> list[QualityResult]:
    ids = [record.entity_id for record in records]
    duplicate_count = sum(count - 1 for count in Counter(ids).values() if count > 1)
    missing_source_refs = sum(not record.source_id or not record.run_id for record in records)
    return [
        QualityResult(check_id="schema_valid", status="fail" if not records else "pass", observed_value=len(records), details="No entity records" if not records else None),
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
        QualityResult(check_id="schema_valid", status="warn" if not records else "pass", observed_value=len(records), details="No research works returned" if not records else None),
        QualityResult(check_id="identifier_unique", status="fail" if duplicate_count else "pass", observed_value=duplicate_count, threshold=0),
        QualityResult(check_id="source_ref_present", status="fail" if missing_source_refs else "pass", observed_value=missing_source_refs, threshold=0),
    ]


def validate_patent_records(records: list[dict]) -> list[QualityResult]:
    patent_ids = [record.get("patent_id") for record in records]
    duplicate_count = len(patent_ids) - len(set(patent_ids))
    missing_required = sum(not record.get("patent_id") or not record.get("title") for record in records)
    missing_source_refs = sum(not record.get("source_record_id") for record in records)
    return [
        QualityResult(check_id="patent_schema_valid", status="fail" if missing_required else "pass", observed_value=missing_required, threshold=0),
        QualityResult(check_id="patent_identifier_unique", status="fail" if duplicate_count else "pass", observed_value=duplicate_count, threshold=0),
        QualityResult(check_id="patent_source_ref_present", status="fail" if missing_source_refs else "pass", observed_value=missing_source_refs, threshold=0),
        QualityResult(check_id="patent_result_count", status="warn" if not records else "pass", observed_value=len(records), details="No patent records returned" if not records else None),
    ]
