from __future__ import annotations

import re
from dataclasses import dataclass
from difflib import SequenceMatcher


def _normalize(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.casefold())


@dataclass(frozen=True)
class MatchCandidate:
    query: str
    candidate_entity_id: str
    score: float
    method: str
    review_status: str = "unreviewed"


def suggest_match(query: str, candidates: list[tuple[str, str]], threshold: float = 0.70) -> list[MatchCandidate]:
    normalized_query = _normalize(query)
    results = []
    for entity_id, name in candidates:
        score = SequenceMatcher(None, normalized_query, _normalize(name)).ratio()
        if score >= threshold:
            results.append(MatchCandidate(query, entity_id, round(score, 6), "normalized_name_similarity"))
    return sorted(results, key=lambda item: item.score, reverse=True)
