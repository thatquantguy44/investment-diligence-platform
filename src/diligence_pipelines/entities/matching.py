from __future__ import annotations

import json
import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path


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


LEGAL_SUFFIXES = re.compile(r"[\s,]+(inc|incorporated|corp|corporation|co|company|ltd|limited|llc|plc|pte|ag|gmbh|sa|nv|bv|holdings?)\.?$", re.IGNORECASE)


def load_entity_candidates(path: Path) -> list[tuple[str, str]]:
    """Read (entity_id, canonical_name) pairs from a Pipeline 01 entities JSONL file."""
    candidates = []
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if row.get("entity_id") and row.get("canonical_name"):
            candidates.append((row["entity_id"], row["canonical_name"]))
    return candidates


def mention_name(name: str) -> str:
    """Strip trailing legal-form suffixes so 'Acme Robotics Pte. Ltd.' is mentioned as 'Acme Robotics'."""
    previous = None
    stripped = name.strip()
    while previous != stripped:
        previous = stripped
        stripped = LEGAL_SUFFIXES.sub("", stripped).strip(" ,.")
    return stripped or name.strip()


def find_entity_mentions(text: str, candidates: list[tuple[str, str]]) -> list[dict]:
    """Return exact, case-insensitive, word-bounded name mentions; these are unreviewed leads."""
    mentions = []
    for entity_id, name in candidates:
        needle = mention_name(name)
        if len(needle) < 3:
            continue
        match = re.search(rf"(?<!\w){re.escape(needle)}(?!\w)", text, re.IGNORECASE)
        if match:
            mentions.append({"entity_id": entity_id, "mention": match.group(0), "start": match.start(), "end": match.end(), "match_method": "exact_name_mention"})
    return mentions
