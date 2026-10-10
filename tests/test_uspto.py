from diligence_pipelines.sources.uspto import normalize_patents


def test_patent_normalization_creates_records_and_edges():
    payload = b'''{"patents":[{"patent_id":"1","patent_title":"Example Patent","patent_date":"2024-01-01","inventors":[{"inventor_id":"I1","inventor_name_first":"Ada","inventor_name_last":"Example"}],"assignees":[{"assignee_id":"A1","assignee_organization":"Example Co"}]}]}'''
    patents, assignments, inventors = normalize_patents(payload, "run-1", "source:1")
    assert patents[0]["patent_id"] == "1"
    assert assignments[0]["assignee_id"] == "A1"
    assert inventors[0]["inventor_id"] == "I1"
