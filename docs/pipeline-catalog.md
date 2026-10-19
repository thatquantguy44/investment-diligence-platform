# Pipeline catalog

| Pipeline | Status | Initial output | Current implementation |
| --- | --- | --- | --- |
| 01 Entity graph | prototype | entities, aliases, relationships, match candidates | fixture-backed entity publication |
| 02 Technology and talent | pilot | patents, research works, inventor and institution edges | OpenAlex + USPTO/PatentsView bounded slice |
| 03 Trade exposure | pilot | trade flows, concentration, mirror discrepancies | bounded UN Comtrade-compatible slice |
| 04 Public awards | pilot | awards, award events, recipients, classification tags, recipient concentration | bounded USAspending contracts/grants slice with modification history |
| 05 Multilingual events | prototype | source documents, event candidates, entity-event edges, event signal counts | GDELT DOC discovery with rule-based, evidence-checked headline extraction |
