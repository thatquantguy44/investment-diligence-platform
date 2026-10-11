export const graph = {
  nodes: [
    { id: 'sec', name: 'SEC EDGAR', kind: 'Source', type: 'source', pipe: '01', x: 95, y: 125, fields: { source: 'sec_edgar', endpoint: 'data.sec.gov/submissions', policy: 'Public source capture' } },
    { id: 'gleif', name: 'GLEIF', kind: 'Source', type: 'source', pipe: '01', x: 95, y: 330, fields: { source: 'gleif', endpoint: 'api.gleif.org', policy: 'Optional LEI enrichment' } },
    { id: 'openalex', name: 'OpenAlex', kind: 'Source', type: 'source', pipe: '02', x: 95, y: 510, fields: { source: 'openalex', endpoint: 'api.openalex.org/works', policy: 'Public research metadata; no key required' } },
    { id: 'raw-sec', name: 'Raw SEC capture', kind: 'Immutable capture', type: 'capture', pipe: '01', x: 275, y: 125, fields: { source_record_id: 'source:<sha256>', adapter: 'sec-submissions-1.0.0', status: 'HTTP 200', storage: 'raw/sec_edgar/<hash>.bin' } },
    { id: 'raw-gleif', name: 'Raw LEI capture', kind: 'Immutable capture', type: 'capture', pipe: '01', x: 275, y: 330, fields: { source_record_id: 'source:<sha256>', adapter: 'gleif-lei-record-1.0.0', status: 'HTTP 200', storage: 'raw/gleif/<hash>.bin' } },
    { id: 'raw-oa', name: 'Raw works capture', kind: 'Immutable capture', type: 'capture', pipe: '02', x: 275, y: 510, fields: { source_record_id: 'source:<sha256>', adapter: 'openalex-works-1.0.0', status: 'HTTP 200', storage: 'raw/openalex/<hash>.bin' } },
    { id: 'apple', name: 'Apple Inc.', kind: 'Entity · CIK 0000320193', type: 'entity', pipe: '01', x: 500, y: 170, fields: { entity_id: 'entity:sec:0000320193', identifier: 'SEC CIK 0000320193', status: 'active', review: 'source-derived' } },
    { id: 'energy', name: 'Example Energy', kind: 'Entity · fixture', type: 'entity', pipe: '01', x: 500, y: 390, fields: { entity_id: 'entity:example-energy', identifier: 'fixture organization', status: 'unknown', review: 'unreviewed' } },
    { id: 'patent', name: 'Synthetic battery separator', kind: 'Patent · 10905426', type: 'patent', pipe: '02', x: 720, y: 145, fields: { patent_id: '10905426', source: 'USPTO fixture', date: '2021-02-02', review: 'source evidence' } },
    { id: 'research', name: 'Solid-state battery study', kind: 'Research work · W123', type: 'research', pipe: '02', x: 720, y: 315, fields: { work_id: 'https://openalex.org/W123', source: 'OpenAlex fixture', date: '2024-01-01', citations: '4' } },
    { id: 'inventor', name: 'Ada Example', kind: 'Inventor / author', type: 'person', pipe: '02', x: 720, y: 485, fields: { role: 'appears as inventor / author', evidence: 'patent and authorship records', review: 'not employment evidence' } },
    { id: 'university', name: 'Example University', kind: 'Institution', type: 'institution', pipe: '02', x: 1000, y: 220, fields: { institution_id: 'https://openalex.org/I123', role: 'authorship institution', review: 'source-derived' } },
    { id: 'topic', name: 'Solid-state battery', kind: 'Topic observation', type: 'topic', pipe: '02', x: 1000, y: 400, fields: { formula: 'deterministic query/topic observation', window: 'query-bounded run', confidence: 'metadata signal only' } },
    { id: 'lei', name: 'LEI alias', kind: 'Exact identifier alias', type: 'capture', pipe: '01', x: 1000, y: 105, fields: { match_method: 'lei_exact', score: '1.0', review_status: 'accepted', caveat: 'alias, not ownership proof' } }
  ],
  edges: [
    { a: 'sec', b: 'raw-sec', label: 'fetches', className: 'source' }, { a: 'gleif', b: 'raw-gleif', label: 'enriches', className: 'source' }, { a: 'openalex', b: 'raw-oa', label: 'fetches', className: 'source' },
    { a: 'raw-sec', b: 'apple', label: 'normalizes' }, { a: 'raw-gleif', b: 'apple', label: 'alias evidence' }, { a: 'apple', b: 'lei', label: 'identifier' },
    { a: 'raw-oa', b: 'research', label: 'normalizes' }, { a: 'energy', b: 'patent', label: 'assignee record', className: 'candidate' }, { a: 'patent', b: 'inventor', label: 'inventor record' },
    { a: 'research', b: 'inventor', label: 'authorship' }, { a: 'research', b: 'university', label: 'institution' }, { a: 'research', b: 'topic', label: 'topic observation' }, { a: 'patent', b: 'topic', label: 'query match' },
    { a: 'energy', b: 'research', label: 'candidate association', className: 'candidate' }
  ]
};
