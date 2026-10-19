from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Protocol, Sequence

import yaml

from diligence_pipelines.entities.matching import find_entity_mentions


EVENT_SCHEMA_VERSION = "event_candidate.v1"

# Latin-script patterns are word-bounded; CJK patterns are plain substrings because those scripts do not use spaces.
EVENT_RULES: dict[str, dict[str, list[str]]] = {
    "funding_round": {
        "latin": [r"raises? \$?[\d.,]+\s*(?:m|mn|million|b|bn|billion)", r"series [a-f] (?:round|funding)", r"seed (?:round|funding)", r"funding round", r"secures? (?:\$?[\d.,]+\s*(?:m|million|b|billion) )?(?:in )?funding", r"ronda de financiaci[oó]n", r"lev[ée]e de fonds", r"finanzierungsrunde"],
        "cjk": ["融资", "資金調達"],
    },
    "acquisition": {
        "latin": [r"acquires?", r"acquisition of", r"to acquire", r"agrees? to buy", r"takeover", r"merger", r"merges? with", r"adquiere", r"adquisici[oó]n", r"rach[eè]te", r"übernimmt", r"übernahme"],
        "cjk": ["收购", "并购", "買収"],
    },
    "partnership": {
        "latin": [r"partners? with", r"partnership", r"joint venture", r"teams? up with", r"strategic alliance", r"collaborat(?:es|ion) with", r"alianza", r"partenariat", r"kooperation"],
        "cjk": ["合作", "提携"],
    },
    "facility": {
        "latin": [r"new (?:plant|factory|facility|fab)", r"gigafactory", r"breaks? ground", r"opens? (?:a |its |new )?(?:plant|factory|facility|fab)", r"expands? (?:plant|factory|facility|production)", r"nueva planta", r"nouvelle usine", r"neues werk"],
        "cjk": ["工厂", "工場", "建厂"],
    },
    "workforce_reduction": {
        "latin": [r"lay(?:s)? off", r"layoffs?", r"job cuts?", r"cuts? [\d,]+ jobs", r"cuts? jobs", r"despidos", r"licenciements", r"stellenabbau"],
        "cjk": ["裁员", "人員削減"],
    },
    "regulatory_action": {
        "latin": [r"fined", r"antitrust", r"probe", r"investigat(?:ion|es|ed)", r"sanctions?", r"export controls?", r"entity list", r"recall(?:s|ed)?", r"multa", r"amende", r"bußgeld"],
        "cjk": ["处罚", "制裁", "調査"],
    },
    "government_award": {
        "latin": [r"wins? (?:a |an )?(?:\$?[\d.,]+\s*(?:m|million|b|billion) )?contract", r"awarded (?:a |an )?(?:\$?[\d.,]+\s*(?:m|million|b|billion) )?(?:contract|grant)", r"(?:receives?|secures?) (?:a |an )?(?:federal |government )?grant", r"chips act"],
        "cjk": ["中标", "補助金"],
    },
    "product_launch": {
        "latin": [r"launch(?:es|ed)?", r"unveils?", r"introduces?", r"debuts?", r"lanza", r"stellt .* vor"],
        "cjk": ["发布", "発表"],
    },
    "leadership_change": {
        "latin": [r"appoints?", r"names? (?:new )?(?:ceo|cfo|cto|chief)", r"steps? down", r"resigns?", r"new ceo", r"nombra", r"nomme"],
        "cjk": ["任命", "辞任"],
    },
    "legal_dispute": {
        "latin": [r"sues?", r"lawsuit", r"files? suit", r"settles?", r"settlement", r"patent infringement", r"demanda", r"poursuite", r"klage"],
        "cjk": ["起诉", "訴訟"],
    },
    "insolvency": {
        "latin": [r"bankruptcy", r"chapter 11", r"insolven(?:t|cy)", r"files? for protection", r"quiebra", r"faillite", r"insolvenz"],
        "cjk": ["破产", "破産"],
    },
}
RULES_VERSION = "event_rules.v1"


def load_event_query(name: str, path: Path) -> str:
    """Return one named GDELT query preset from the event queries YAML file."""
    sectors = (yaml.safe_load(path.read_text()) or {}).get("sectors") or {}
    if name not in sectors or not sectors[name].get("query"):
        raise ValueError(f"Unknown event sector {name!r}; choose from: {', '.join(sorted(sectors))}")
    return str(sectors[name]["query"])


@dataclass(frozen=True)
class ExtractorInfo:
    extractor_id: str
    model_name: str
    model_revision: str
    prompt_version: str
    schema_version: str = EVENT_SCHEMA_VERSION


class EventExtractor(Protocol):
    info: ExtractorInfo

    def extract(self, document: dict) -> list[dict]:
        """Return candidate dicts with event_type, excerpt, start, end, and confidence."""


class RuleBasedEventExtractor:
    """Deterministic keyword extractor over document titles.

    It is the reference extractor for the evidence and validation contract. A
    local LLM extractor can replace it by implementing ``EventExtractor`` and
    returning exact spans; validation rejects any excerpt not found in the source text.
    """

    info = ExtractorInfo(extractor_id="rule_based", model_name="none", model_revision=RULES_VERSION, prompt_version="none")

    def __init__(self) -> None:
        self._compiled = {
            event_type: [re.compile(rf"(?<!\w){pattern}(?!\w)", re.IGNORECASE) for pattern in rules["latin"]] + [re.compile(re.escape(term)) for term in rules["cjk"]]
            for event_type, rules in EVENT_RULES.items()
        }

    def extract(self, document: dict) -> list[dict]:
        text = document.get("title") or ""
        candidates = []
        for event_type, patterns in self._compiled.items():
            match = next((found for pattern in patterns if (found := pattern.search(text))), None)
            if match:
                candidates.append({"event_type": event_type, "excerpt": match.group(0), "start": match.start(), "end": match.end(), "confidence": 0.4})
        return candidates


def derive_event_outputs(
    documents: Sequence[dict],
    extractor: EventExtractor,
    *,
    entity_candidates: list[tuple[str, str]] | None = None,
    content_sha256: str,
) -> dict[str, list[dict]]:
    candidates = []
    edges = []
    for document in documents:
        if document.get("duplicate_of"):
            continue  # Syndicated copies corroborate the original; they do not create new candidates.
        mentions = find_entity_mentions(document["title"], entity_candidates or [])
        for found in extractor.extract(document):
            candidate_id = f"{document['document_id']}:{found['event_type']}"
            candidates.append({
                "record_id": f"event_candidate:{candidate_id}",
                "schema_version": "1.0.0",
                "pipeline_id": "05_multilingual_events",
                "event_candidate_id": candidate_id,
                "document_id": document["document_id"],
                "event_type": found["event_type"],
                "status": "candidate",
                "confidence": found["confidence"],
                # Headlines rarely state when the event happened; report time is GDELT first-seen time.
                "event_time": None,
                "report_time": document.get("first_seen_at"),
                "language": document.get("language"),
                "evidence": {
                    "source_record_id": document["source_record_id"],
                    "locator": f"title[{found['start']}:{found['end']}]",
                    "quote_or_excerpt": found["excerpt"],
                    "content_sha256": content_sha256,
                },
                "entity_ids": sorted({mention["entity_id"] for mention in mentions}),
                "extractor": asdict(extractor.info),
            })
            for mention in mentions:
                edges.append({
                    "record_id": f"entity_event_edge:{mention['entity_id']}:{candidate_id}",
                    "schema_version": "1.0.0",
                    "pipeline_id": "05_multilingual_events",
                    "entity_id": mention["entity_id"],
                    "event_candidate_id": candidate_id,
                    "mention": mention["mention"],
                    "locator": f"title[{mention['start']}:{mention['end']}]",
                    "match_method": mention["match_method"],
                    "review_status": "unreviewed",
                })

    syndication_domains: dict[str, set[str]] = defaultdict(set)
    for document in documents:
        syndication_domains[document["syndication_key"]].add(document["domain"])
    document_by_id = {document["document_id"]: document for document in documents}

    grouped: dict[tuple[str, str, str], list[dict]] = defaultdict(list)
    for candidate in candidates:
        day = (candidate["report_time"] or "unknown")[:10]
        for entity_id in candidate["entity_ids"] or ["unmatched"]:
            grouped[(entity_id, candidate["event_type"], day)].append(candidate)
    signals = []
    for (entity_id, event_type, day), rows in sorted(grouped.items()):
        domains = set()
        for row in rows:
            domains |= syndication_domains[document_by_id[row["document_id"]]["syndication_key"]]
        signals.append({
            "record_id": f"event_signal:{entity_id}:{event_type}:{day}",
            "schema_version": "1.0.0",
            "pipeline_id": "05_multilingual_events",
            "entity_id": entity_id,
            "event_type": event_type,
            "report_date": day,
            "candidate_count": len(rows),
            "distinct_domain_count": len(domains),
            "event_candidate_ids": sorted(row["event_candidate_id"] for row in rows),
            "formula_version": "event_signal_counts.v1: candidates and distinct reporting domains (incl. syndicated copies) per entity, event type, and report date",
        })
    return {"event_candidates": candidates, "entity_event_edges": edges, "event_signal_counts": signals}


def event_coverage_report(documents: Sequence[dict], outputs: dict[str, list[dict]], source_metadata: dict) -> dict:
    with_candidates = {row["document_id"] for row in outputs["event_candidates"]}
    languages: dict[str, int] = defaultdict(int)
    for document in documents:
        languages[document.get("language") or "unknown"] += 1
    return {
        "input_document_count": len(documents),
        "syndicated_duplicate_count": sum(bool(document.get("duplicate_of")) for document in documents),
        "documents_with_candidates": len(with_candidates),
        "documents_without_candidates": sum(1 for document in documents if not document.get("duplicate_of") and document["document_id"] not in with_candidates),
        "documents_by_language": dict(sorted(languages.items())),
        "candidate_count": len(outputs["event_candidates"]),
        "entity_linked_candidate_count": sum(bool(row["entity_ids"]) for row in outputs["event_candidates"]),
        "source_returned_row_count": source_metadata.get("returned_row_count"),
        "limitations": [
            "GDELT is a discovery index, not a complete news archive or an authority on the truth of a claim.",
            "Event candidates are extracted from headlines only and remain unverified until analyst review or primary-source confirmation.",
            "Keyword rules have limited non-English coverage; documents without candidates are not evidence that no event occurred.",
            "Entity links are exact name mentions and remain unreviewed.",
        ],
    }
