from __future__ import annotations

from collections.abc import Sequence


def derive_topic_observation(records: Sequence[dict], query: str, run_id: str) -> dict:
    dates = sorted(record["publication_date"] for record in records if record.get("publication_date"))
    input_ids = [record["record_id"] for record in records]
    return {
        "record_id": f"observation:openalex:{run_id}:work_count",
        "schema_version": "1.0.0", "pipeline_id": "02_technology_talent", "source_id": "openalex", "run_id": run_id,
        "observation_id": f"observation:openalex:{run_id}:work_count", "entity_id": None,
        "metric": "research_work_count", "value": float(len(records)), "unit": "works",
        "period_start": dates[0] if dates else None, "period_end": dates[-1] if dates else None,
        "input_record_ids": input_ids, "formula_version": "research_work_count.v1",
        "limitations": [f"OpenAlex search results for query: {query}", "Research metadata is not evidence of employment, ownership, or technology quality."],
    }


def derive_institution_edges(records: Sequence[dict], run_id: str) -> list[dict]:
    edges = []
    seen = set()
    for record in records:
        for institution in record.get("institutions", []):
            institution_id = institution.get("id") or f"name:{institution.get('name', '')}"
            key = (record["work_id"], institution_id)
            if key in seen:
                continue
            seen.add(key)
            edges.append({
                "record_id": f"institution_edge:{record['work_id']}:{institution_id}",
                "schema_version": "1.0.0", "pipeline_id": "02_technology_talent", "source_id": "openalex", "run_id": run_id,
                "work_id": record["work_id"], "institution_id": institution_id,
                "institution_name": institution.get("name"), "source_record_id": record["source_record_id"],
                "relationship_type": "authorship_affiliation",
                "limitations": ["Affiliation is not evidence of employment by a target company."],
            })
    return edges
