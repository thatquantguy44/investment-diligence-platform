from diligence_pipelines.sources.openalex import normalize_openalex_works


def test_openalex_normalization_preserves_research_provenance():
    payload = b'''{"results":[{"id":"https://openalex.org/W1","title":"A Research Work","publication_date":"2024-01-01","type":"article","cited_by_count":3,"authorships":[{"author":{"id":"https://openalex.org/A1","display_name":"Ada Example"},"institutions":[{"id":"https://openalex.org/I1","display_name":"Example University"}]}]}]}'''
    records = normalize_openalex_works(payload, "run-1", "source:abc")
    assert records[0]["work_id"].endswith("W1")
    assert records[0]["source_record_id"] == "source:abc"
    assert records[0]["institutions"][0]["name"] == "Example University"
