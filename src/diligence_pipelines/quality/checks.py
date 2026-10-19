from __future__ import annotations

import re
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


def validate_trade_flows(records: list[dict], coverage: dict | None = None, source_metadata: dict | None = None) -> list[QualityResult]:
    identifiers = [record.get("trade_flow_id") for record in records]
    duplicate_count = len(identifiers) - len(set(identifiers))
    missing_required = sum(not record.get("trade_flow_id") or not record.get("period") or record.get("trade_value_usd") is None for record in records)
    missing_source_refs = sum(not record.get("source_record_id") for record in records)
    return [
        QualityResult(check_id="trade_schema_valid", status="fail" if missing_required else "pass", observed_value=missing_required, threshold=0),
        QualityResult(check_id="trade_identifier_unique", status="fail" if duplicate_count else "pass", observed_value=duplicate_count, threshold=0),
        QualityResult(check_id="trade_source_ref_present", status="fail" if missing_source_refs else "pass", observed_value=missing_source_refs, threshold=0),
        QualityResult(check_id="trade_result_count", status="warn" if not records else "pass", observed_value=len(records), details="No trade flows returned" if not records else None),
        QualityResult(check_id="coverage_report_present", status="pass" if coverage else "fail", observed_value=1 if coverage else 0, threshold=1),
        QualityResult(
            check_id="trade_configured_coverage",
            status="fail" if coverage and coverage.get("missing_hs_codes") else "pass",
            observed_value=coverage.get("missing_hs_codes", []) if coverage else None,
            details="Configured HS codes were not returned" if coverage and coverage.get("missing_hs_codes") else None,
        ),
        QualityResult(
            check_id="trade_source_metadata_present",
            status="fail" if not source_metadata or source_metadata.get("error") else "pass",
            observed_value=0 if not source_metadata else 1,
            threshold=1,
            details=(source_metadata or {}).get("error") or ("Response metadata unavailable" if not source_metadata else None),
        ),
    ]


def validate_awards(awards: list[dict], events: list[dict], coverage: dict | None = None, source_metadata: dict | None = None) -> list[QualityResult]:
    award_ids = [record.get("award_id") for record in awards]
    duplicate_count = len(award_ids) - len(set(award_ids))
    missing_required = sum(not record.get("award_id") or not record.get("recipient_name") or not record.get("award_group") for record in awards)
    missing_source_refs = sum(not record.get("source_record_id") for record in [*awards, *events])
    event_ids = [event.get("award_event_id") for event in events]
    duplicate_events = len(event_ids) - len(set(event_ids))
    known_awards = set(award_ids)
    orphan_events = sum(event.get("award_id") not in known_awards for event in events)
    return [
        QualityResult(check_id="award_schema_valid", status="fail" if missing_required else "pass", observed_value=missing_required, threshold=0),
        QualityResult(check_id="award_identifier_unique", status="fail" if duplicate_count else "pass", observed_value=duplicate_count, threshold=0),
        QualityResult(check_id="award_source_ref_present", status="fail" if missing_source_refs else "pass", observed_value=missing_source_refs, threshold=0),
        QualityResult(check_id="award_result_count", status="warn" if not awards else "pass", observed_value=len(awards), details="No awards returned" if not awards else None),
        QualityResult(check_id="award_event_identifier_unique", status="fail" if duplicate_events else "pass", observed_value=duplicate_events, threshold=0),
        QualityResult(check_id="award_event_award_ref_valid", status="fail" if orphan_events else "pass", observed_value=orphan_events, threshold=0, details="Award events reference awards outside this run" if orphan_events else None),
        QualityResult(check_id="award_coverage_report_present", status="pass" if coverage else "fail", observed_value=1 if coverage else 0, threshold=1),
        QualityResult(
            check_id="award_result_not_truncated",
            status="warn" if coverage and coverage.get("result_truncated") else "pass",
            observed_value=bool(coverage and coverage.get("result_truncated")),
            details="More matching awards exist than --max-records allowed" if coverage and coverage.get("result_truncated") else None,
        ),
        QualityResult(
            check_id="award_source_metadata_present",
            status="fail" if not source_metadata or source_metadata.get("error") else "pass",
            observed_value=0 if not source_metadata else 1,
            threshold=1,
            details=(source_metadata or {}).get("error") or ("Response metadata unavailable" if not source_metadata else None),
        ),
    ]


def validate_event_candidates(documents: list[dict], candidates: list[dict], coverage: dict | None = None, source_metadata: dict | None = None) -> list[QualityResult]:
    document_ids = [document.get("document_id") for document in documents]
    duplicate_documents = len(document_ids) - len(set(document_ids))
    titles = {document.get("document_id"): document.get("title") or "" for document in documents}
    missing_documents = sum(candidate.get("document_id") not in titles for candidate in candidates)
    unsupported = 0
    for candidate in candidates:
        evidence = candidate.get("evidence") or {}
        excerpt = evidence.get("quote_or_excerpt")
        match = re.fullmatch(r"title\[(\d+):(\d+)\]", evidence.get("locator") or "")
        text = titles.get(candidate.get("document_id"), "")
        if not excerpt or not match or text[int(match.group(1)):int(match.group(2))] != excerpt:
            unsupported += 1
    extractor_fields = ("extractor_id", "model_name", "model_revision", "prompt_version", "schema_version")
    missing_extractor = sum(any(not (candidate.get("extractor") or {}).get(field) for field in extractor_fields) for candidate in candidates)
    premature = sum(candidate.get("status") != "candidate" for candidate in candidates)
    candidate_ids = [candidate.get("event_candidate_id") for candidate in candidates]
    duplicate_candidates = len(candidate_ids) - len(set(candidate_ids))
    return [
        QualityResult(check_id="document_identifier_unique", status="fail" if duplicate_documents else "pass", observed_value=duplicate_documents, threshold=0),
        QualityResult(check_id="document_result_count", status="warn" if not documents else "pass", observed_value=len(documents), details="No documents returned" if not documents else None),
        QualityResult(check_id="event_candidate_identifier_unique", status="fail" if duplicate_candidates else "pass", observed_value=duplicate_candidates, threshold=0),
        QualityResult(check_id="event_document_ref_valid", status="fail" if missing_documents else "pass", observed_value=missing_documents, threshold=0),
        QualityResult(check_id="event_evidence_supported", status="fail" if unsupported else "pass", observed_value=unsupported, threshold=0, details="Excerpts must match the source text at their locator" if unsupported else None),
        QualityResult(check_id="event_extractor_recorded", status="fail" if missing_extractor else "pass", observed_value=missing_extractor, threshold=0),
        QualityResult(check_id="event_candidates_unverified", status="fail" if premature else "pass", observed_value=premature, threshold=0, details="Extracted events must stay candidates until reviewed" if premature else None),
        QualityResult(check_id="event_coverage_report_present", status="pass" if coverage else "fail", observed_value=1 if coverage else 0, threshold=1),
        QualityResult(
            check_id="event_source_metadata_present",
            status="fail" if not source_metadata or source_metadata.get("error") else "pass",
            observed_value=0 if not source_metadata else 1,
            threshold=1,
            details=(source_metadata or {}).get("error") or ("Response metadata unavailable" if not source_metadata else None),
        ),
    ]
