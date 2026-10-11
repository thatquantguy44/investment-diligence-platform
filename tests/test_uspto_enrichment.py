from pathlib import Path

from diligence_pipelines.sources import enrich_bulk_patents, load_bulk_patent_index


def test_bulk_enrichment_joins_abstract_and_assignee(tmp_path):
    patent_file = tmp_path / "patents.tsv"
    patent_file.write_text("patent_id\tpatent_title\n1\tBattery\n")
    abstract_file = tmp_path / "abstract.tsv"
    abstract_file.write_text("patent_id\tpatent_abstract\n1\tSolid state battery abstract\n")
    assignee_file = tmp_path / "assignee.tsv"
    assignee_file.write_text("patent_id\tassignee_organization\n1\tExample Energy\n")
    records, _ = load_bulk_patent_index(patent_file)
    enriched = enrich_bulk_patents(records, abstract_file, assignee_file)
    assert enriched[0]["abstract"] == "Solid state battery abstract"
    assert enriched[0]["assignee_name"] == "Example Energy"
