import json
from pathlib import Path

from diligence_pipelines.cli import apply_entity_match_review
from diligence_pipelines.settings import Settings


def test_apply_entity_match_review_publishes_review_states(tmp_path: Path):
    review = tmp_path / "review.yaml"
    review.write_text("""\
review_queue_id: demo-review
reviewer: Analyst
publication_policy: accepted_only
candidates:
  - candidate_id: accepted-match
    sector: defense
    source_record_id: recipient:uei:ABC
    source_name: Example Recipient
    candidate_entity_id: entity:sec:0000000001
    candidate_entity_name: Example Corp
    match_method: normalized_name_similarity
    match_score: 1.0
    review_status: accepted
    decision: accepted
    review_note: Exact source-name match.
  - candidate_id: pending-match
    source_record_id: recipient:uei:DEF
    source_name: Pending Recipient
    candidate_entity_id: entity:sec:0000000002
    candidate_entity_name: Pending Corp
    match_method: normalized_name_similarity
    match_score: 0.8
    review_status: unreviewed
    decision: pending
    review_note: ""
""")

    assert apply_entity_match_review(review, Settings(data_root=tmp_path)) == 0
    output = next(tmp_path.glob("curated/01_entity_graph/*/reviewed_match_candidates.jsonl"))
    records = [json.loads(line) for line in output.read_text().splitlines()]
    assert len(records) == 2
    by_id = {record["candidate_id"]: record for record in records}
    assert by_id["accepted-match"]["review_status"] == "accepted"
    assert by_id["accepted-match"]["reviewer"] == "Analyst"
    assert by_id["accepted-match"]["sector"] == "defense"
    assert by_id["accepted-match"]["published_at"]
    assert by_id["pending-match"]["review_status"] == "unreviewed"
    assert by_id["pending-match"]["reviewer"] is None
