from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Sequence

from diligence_pipelines.events import EVENT_RULES


def load_labeled_examples(path: Path) -> list[dict]:
    """Read JSONL rows of ``{"title": ..., "language": ..., "events": [event_type, ...]}``."""
    examples = []
    for number, line in enumerate(path.read_text().splitlines(), start=1):
        if not line.strip():
            continue
        row = json.loads(line)
        unknown = sorted(set(row.get("events") or []) - set(EVENT_RULES))
        if not row.get("title") or unknown:
            raise ValueError(f"{path}:{number}: needs a title and known event types (unknown: {unknown})")
        examples.append({"title": row["title"], "language": row.get("language"), "events": sorted(set(row.get("events") or []))})
    if not examples:
        raise ValueError(f"{path}: no labeled examples")
    return examples


def _scores(tp: int, fp: int, fn: int) -> dict:
    precision = tp / (tp + fp) if tp + fp else None
    recall = tp / (tp + fn) if tp + fn else None
    f1 = 2 * precision * recall / (precision + recall) if precision and recall else (0.0 if tp + fp + fn else None)
    return {"tp": tp, "fp": fp, "fn": fn, "precision": precision, "recall": recall, "f1": f1}


def evaluate_extractor(extractor, examples: Sequence[dict]) -> dict:
    """Score an extractor against labeled headlines at the (headline, event type) level."""
    counts: dict[str, list[int]] = defaultdict(lambda: [0, 0, 0])
    by_language: dict[str, list[int]] = defaultdict(lambda: [0, 0, 0])
    predictions = []
    for index, example in enumerate(examples):
        found = extractor.extract({"document_id": f"eval:{index}", "title": example["title"], "language": example.get("language")})
        predicted = sorted({item["event_type"] for item in found})
        expected = example["events"]
        predictions.append({"title": example["title"], "language": example.get("language"), "expected": expected, "predicted": predicted})
        for event_type in set(predicted) | set(expected):
            slot = 0 if event_type in predicted and event_type in expected else 1 if event_type in predicted else 2
            counts[event_type][slot] += 1
            by_language[example.get("language") or "unknown"][slot] += 1
    total = [sum(values[slot] for values in counts.values()) for slot in range(3)]
    info = extractor.info
    return {
        "extractor": {"extractor_id": info.extractor_id, "model_name": info.model_name, "model_revision": info.model_revision, "prompt_version": info.prompt_version},
        "example_count": len(examples),
        "exact_match_rate": sum(row["expected"] == row["predicted"] for row in predictions) / len(predictions),
        "micro": _scores(*total),
        "by_event_type": {event_type: _scores(*values) for event_type, values in sorted(counts.items())},
        "by_language": {language: _scores(*values) for language, values in sorted(by_language.items())},
        "mismatches": [row for row in predictions if row["expected"] != row["predicted"]],
        "extractor_stats": dict(getattr(extractor, "stats", {}) or {}) or None,
    }


def compare_extractors(candidate: dict, baseline: dict) -> dict:
    """Headlines where two evaluation reports disagree, plus the micro-F1 change."""
    baseline_by_title = {row["title"]: row for row in baseline["mismatches"]}
    candidate_by_title = {row["title"]: row for row in candidate["mismatches"]}
    return {
        "candidate": candidate["extractor"]["extractor_id"],
        "baseline": baseline["extractor"]["extractor_id"],
        "micro_f1_delta": (candidate["micro"]["f1"] or 0.0) - (baseline["micro"]["f1"] or 0.0),
        "only_candidate_wrong": sorted(set(candidate_by_title) - set(baseline_by_title)),
        "only_baseline_wrong": sorted(set(baseline_by_title) - set(candidate_by_title)),
    }
