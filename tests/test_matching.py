from diligence_pipelines.entities import suggest_match


def test_matching_returns_unreviewed_candidates():
    matches = suggest_match("Acme Robotics", [("entity:1", "Acme Robotics Pte. Ltd.")])
    assert matches and matches[0].review_status == "unreviewed"
