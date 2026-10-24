import React, { useEffect, useMemo, useRef, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { graph as fixtureGraph } from './data';
import './styles.css';

const emptyGraph = { nodes: [], edges: [] };

const guidedStories = [
  {
    id: 'ai-cyber-mission',
    eyebrow: 'Scenario 01 · Public awards',
    title: 'AI, cyber & mission software',
    summary: 'Trace a bounded Department of Defense award from its public source to the reported recipient.',
    steps: [
      {
        title: 'Start at the public spending source',
        body: 'USAspending provides the original government-award record. This demo uses a deliberately bounded 2024 Department of Defense slice—not a claim about the full market.',
        resolve: (graph) => findNode(graph, [(node) => node.type === 'source' && node.name.toLowerCase().includes('usaspending')]),
      },
      {
        title: 'Inspect a cyber mission record',
        body: 'The award retains its public identifier, agency, classification, obligation amount, source link, and text supplied by USAspending.',
        resolve: (graph) => findNode(graph, [
          (node) => node.type === 'award' && (node.fields.description || '').toLowerCase().includes('cybersecurity'),
          (node) => node.type === 'award' && String(node.fields.naics_code || '').startsWith('541'),
          (node) => node.type === 'award',
        ]),
      },
      {
        title: 'Keep the conclusion bounded',
        body: 'The recipient is a reported award recipient. An obligation is not evidence of performance, payment, revenue, or a confirmed canonical-company match.',
        resolve: (graph) => {
          const award = guidedStories[0].steps[1].resolve(graph);
          return findNeighbor(graph, award?.id, (node) => node.type === 'recipient') || award;
        },
      },
    ],
  },
  {
    id: 'defense-sensing',
    eyebrow: 'Scenario 02 · Public awards',
    title: 'Defense electronics & sensing',
    summary: 'Explore a bounded DoD electronics, sensing, and communications award slice.',
    steps: [
      {
        title: 'Anchor on USAspending',
        body: 'The scenario begins with the public source rather than a thematic inference. The extraction is limited to selected defense-electronics classifications and a 2024 DoD window.',
        resolve: (graph) => findNode(graph, [(node) => node.type === 'source' && node.name.toLowerCase().includes('usaspending')]),
      },
      {
        title: 'Open a sensing award record',
        body: 'The record preserves the agency, classification, reported recipient, obligation, and original USAspending link for review.',
        resolve: (graph) => findNode(graph, [
          (node) => node.type === 'award' && (node.fields.description || '').toLowerCase().includes('an/spy'),
          (node) => node.type === 'award' && node.fields.naics_code === '334511',
          (node) => node.type === 'award',
        ]),
      },
      {
        title: 'Trace the reported recipient',
        body: 'The recipient relationship is source-reported. It is intentionally distinct from an analyst-reviewed ownership or entity-resolution conclusion.',
        resolve: (graph) => {
          const award = guidedStories[1].steps[1].resolve(graph);
          return findNeighbor(graph, award?.id, (node) => node.type === 'recipient') || award;
        },
      },
    ],
  },
  {
    id: 'cybersecurity-landscape',
    eyebrow: 'Scenario 03 · Technology evidence',
    title: 'Cybersecurity technology landscape',
    summary: 'Compare source-bounded cybersecurity research and patent records without inventing a linkage between them.',
    steps: [
      {
        title: 'Start with the research source',
        body: 'OpenAlex returns a bounded set of research metadata records. Author and institution associations remain metadata, not evidence of current employment or commercial relevance.',
        resolve: (graph) => findNode(graph, [(node) => node.type === 'source' && node.name.toLowerCase().includes('openalex')]),
      },
      {
        title: 'Inspect a cybersecurity research record',
        body: 'Each work retains its identifier, publication date, source record, and named metadata relationships for independent review.',
        resolve: (graph) => findNode(graph, [
          (node) => node.type === 'research' && node.name.toLowerCase().includes('cybersecurity'),
          (node) => node.type === 'research',
        ]),
      },
      {
        title: 'Compare the patent evidence boundary',
        body: 'USPTO-derived patent records can corroborate technology activity at the topic level, but this view does not claim that a paper and patent share an owner, author, or commercial outcome.',
        resolve: (graph) => findNode(graph, [
          (node) => node.type === 'patent' && node.name.toLowerCase().includes('cybersecurity'),
          (node) => node.type === 'patent',
        ]),
      },
    ],
  },
];

function findNode(graph, predicates) {
  for (const predicate of predicates) {
    const match = graph.nodes.find(predicate);
    if (match) return match;
  }
  return null;
}

function findNeighbor(graph, nodeId, predicate) {
  if (!nodeId) return null;
  const neighborIds = new Set(graph.edges.flatMap((edge) => {
    if (edge.a === nodeId) return [edge.b];
    if (edge.b === nodeId) return [edge.a];
    return [];
  }));
  return graph.nodes.find((node) => neighborIds.has(node.id) && predicate(node)) || null;
}

function defaultLens(graph) {
  const reviewedEdge = graph.edges.find((edge) => edge.className === 'reviewed');
  const reviewedEntityId = reviewedEdge && [reviewedEdge.a, reviewedEdge.b].find((id) => graph.nodes.find((node) => node.id === id && node.type === 'entity'));
  return findNode(graph, [
    (node) => node.id === reviewedEntityId,
    (node) => node.type === 'entity',
    (node) => node.type === 'institution',
    (node) => node.type === 'topic',
  ]) || graph.nodes[0] || null;
}

function neighborsFor(graph, nodeId) {
  if (!nodeId) return new Set();
  return new Set(graph.edges.flatMap((edge) => edge.a === nodeId ? [edge.b] : edge.b === nodeId ? [edge.a] : []));
}

function entityEvidencePathsFor(graph, nodeId, nodeMap) {
  if (!nodeId || !nodeMap[nodeId]) return [];
  const adjacency = new Map();
  graph.edges.forEach((edge) => {
    adjacency.set(edge.a, [...(adjacency.get(edge.a) || []), { id: edge.b, edge }]);
    adjacency.set(edge.b, [...(adjacency.get(edge.b) || []), { id: edge.a, edge }]);
  });
  const sharedHubs = new Set(['source', 'person', 'institution', 'entity']);
  const visited = new Set([nodeId]);
  const queue = [{ id: nodeId, path: [nodeId] }];
  const paths = [];
  while (queue.length) {
    const current = queue.shift();
    if (current.id !== nodeId && sharedHubs.has(nodeMap[current.id]?.type)) continue;
    (adjacency.get(current.id) || []).forEach(({ id, edge }) => {
      if (!visited.has(id)) {
        visited.add(id);
        const path = [...current.path, id];
        paths.push({ node: nodeMap[id], edge, path });
        queue.push({ id, path });
      }
    });
  }
  return paths.filter((item) => item.node);
}

function evidenceStatus(node) {
  const fields = node?.fields || {};
  const review = `${fields.review || ''} ${fields.review_status || ''} ${fields.status || ''}`.toLowerCase();
  if (!node) return { label: 'Unavailable', tone: 'unavailable', detail: 'No evidence record is selected.' };
  if (review.includes('accepted') || review.includes('verified')) return { label: 'Verified', tone: 'verified', detail: 'Reviewed exact-identifier evidence.' };
  if (review.includes('candidate') || review.includes('unreviewed')) return { label: 'Candidate / unreviewed', tone: 'candidate', detail: 'Requires analyst review before use as a conclusion.' };
  if (node.type === 'topic') return { label: 'Inferred', tone: 'inferred', detail: 'A deterministic topic observation, not a verified relationship.' };
  return { label: 'Source-derived', tone: 'derived', detail: 'Preserved from the cited source record.' };
}

function sourceFor(node, graph, nodeMap) {
  const direct = [...neighborsFor(graph, node?.id)].map((id) => nodeMap[id]).find((candidate) => candidate?.type === 'source');
  if (direct) return direct;
  const intermediate = [...neighborsFor(graph, node?.id)].map((id) => nodeMap[id]).find(Boolean);
  return intermediate && [...neighborsFor(graph, intermediate.id)].map((id) => nodeMap[id]).find((candidate) => candidate?.type === 'source');
}

function lineageFor(node, graph, nodeMap) {
  if (!node) return [];
  const source = sourceFor(node, graph, nodeMap);
  const related = [...neighborsFor(graph, node.id)].map((id) => nodeMap[id]).find((candidate) => candidate && candidate.type !== 'source');
  const kind = node.kind.split(' · ')[0];
  return [source?.name, kind, related && related.kind.split(' · ')[0]].filter(Boolean);
}

function displayValue(key, value) {
  if (value === null || value === undefined || value === '') return 'Not supplied';
  if (key.endsWith('_usd') && typeof value === 'number') return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 }).format(value);
  if (typeof value === 'object') return value.quote_or_excerpt || value.locator || JSON.stringify(value);
  return String(value);
}

function fieldLabel(key) {
  return ({ source_url: 'Original record', source_record_id: 'Source record', source_id: 'Source', retrieved_at: 'Retrieved', publication_date: 'Publication date', base_obligation_date: 'Base obligation date', obligated_amount_usd: 'Obligated amount', total_obligated_usd: 'Total obligated', institution_id: 'Institution ID', work_id: 'Research work', patent_id: 'Patent ID', entity_id: 'Canonical entity', review: 'Evidence classification', review_status: 'Review status' }[key] || key.replaceAll('_', ' ').replace(/\b\w/g, (letter) => letter.toUpperCase()));
}

function App() {
  const [graph, setGraph] = useState(emptyGraph);
  const [mode, setMode] = useState('postgres');
  const [apiState, setApiState] = useState('loading');
  const [apiError, setApiError] = useState('');
  const [filter, setFilter] = useState('all');
  const [query, setQuery] = useState('');
  const [selected, setSelected] = useState(null);
  const [showAllEntities, setShowAllEntities] = useState(false);
  const [showAllRelationships, setShowAllRelationships] = useState(false);
  const [expandedTypes, setExpandedTypes] = useState([]);
  const [clusterPosition, setClusterPosition] = useState({ x: 330, y: 310 });
  const [clusterOpen, setClusterOpen] = useState(false);
  const [evidenceWorkspaceOpen, setEvidenceWorkspaceOpen] = useState(false);
  const [viewport, setViewport] = useState({ x: 0, y: 0, scale: 1 });
  const [storyPickerOpen, setStoryPickerOpen] = useState(false);
  const [activeStoryId, setActiveStoryId] = useState(null);
  const [storyStep, setStoryStep] = useState(0);
  const panRef = useRef(null);
  const normalizedQuery = query.trim().toLowerCase();
  const nodeMap = useMemo(() => Object.fromEntries(graph.nodes.map((node) => [node.id, node])), [graph]);
  const entities = useMemo(() => graph.nodes.filter((node) => node.type === 'entity').sort((a, b) => a.name.localeCompare(b.name)), [graph]);
  const selectedNode = selected ? nodeMap[selected] : null;
  const companyLensValue = showAllEntities ? 'all' : entities.some((entity) => entity.id === selected) ? selected : '';
  const activeStory = guidedStories.find((story) => story.id === activeStoryId) || null;
  const activeStoryStep = activeStory?.steps[storyStep] || null;
  const guidedTarget = useMemo(() => activeStoryStep?.resolve(graph) || null, [activeStoryStep, graph]);
  const effectiveLive = mode === 'postgres' && apiState === 'ready';

  useEffect(() => {
    if (mode !== 'postgres') return;
    let cancelled = false;
    setApiState('loading');
    setApiError('');
    setGraph(emptyGraph);
    fetch('/api/knowledge/graph?limit=120')
      .then(async (response) => {
        const payload = await response.json();
        if (!response.ok) throw new Error(payload.detail || payload.error || 'API request failed');
        return payload;
      })
      .then((payload) => { if (!cancelled) { setGraph(payload); setApiState('ready'); setSelected(defaultLens(payload)?.id || null); setShowAllEntities(false); setShowAllRelationships(false); setExpandedTypes([]); setViewport({ x: 0, y: 0, scale: 1 }); } })
      .catch((error) => { if (!cancelled) { setGraph(fixtureGraph); setApiState('error'); setApiError(error.message || 'Start the local knowledge API and try again.'); setSelected(defaultLens(fixtureGraph)?.id || null); setShowAllEntities(false); setShowAllRelationships(false); } });
    return () => { cancelled = true; };
  }, [mode]);

  useEffect(() => {
    if (!activeStory || !guidedTarget) return;
    setSelected(guidedTarget.id);
    setFilter('all');
    setQuery('');
  }, [activeStory, guidedTarget]);

  useEffect(() => {
    if (!storyPickerOpen) return undefined;
    const closeOnEscape = (event) => { if (event.key === 'Escape') setStoryPickerOpen(false); };
    window.addEventListener('keydown', closeOnEscape);
    return () => window.removeEventListener('keydown', closeOnEscape);
  }, [storyPickerOpen]);

  const visible = (node) => {
    const matchesQuery = !normalizedQuery || `${node.name} ${node.kind}`.toLowerCase().includes(normalizedQuery);
    const matchesFilter = filter === 'all' || (filter === 'sources' ? node.type === 'source' : node.pipe === filter);
    return matchesQuery && matchesFilter;
  };

  const neighborIds = useMemo(() => neighborsFor(graph, selected), [graph, selected]);
  const focusedIds = useMemo(() => new Set(selected ? [selected, ...neighborIds] : []), [selected, neighborIds]);
  const entityEvidencePaths = useMemo(() => entityEvidencePathsFor(graph, selected, nodeMap), [graph, selected, nodeMap]);
  const relationshipIds = useMemo(() => showAllRelationships ? new Set([selected, ...entityEvidencePaths.map((item) => item.node.id)]) : focusedIds, [selected, focusedIds, entityEvidencePaths, showAllRelationships]);
  const renderedNodes = useMemo(() => graph.nodes.filter((node) => visible(node) && (showAllEntities ? node.type === 'entity' : (!selected || relationshipIds.has(node.id) || expandedTypes.includes(node.type)))), [graph, selected, relationshipIds, expandedTypes, filter, normalizedQuery, showAllEntities]);
  const renderedNodeMap = useMemo(() => Object.fromEntries(renderedNodes.map((node) => [node.id, node])), [renderedNodes]);
  const renderedEdges = useMemo(() => graph.edges.filter((edge) => renderedNodeMap[edge.a] && renderedNodeMap[edge.b]), [graph, renderedNodeMap]);
  const clusters = useMemo(() => {
    if (!selected || showAllEntities) return [];
    const counts = new Map();
    graph.nodes.filter((node) => visible(node) && !relationshipIds.has(node.id) && !expandedTypes.includes(node.type)).forEach((node) => counts.set(node.type, (counts.get(node.type) || 0) + 1));
    return [...counts.entries()].map(([type, count]) => ({ type, count })).sort((a, b) => b.count - a.count);
  }, [graph, selected, relationshipIds, expandedTypes, filter, normalizedQuery, showAllEntities]);
  const metrics = useMemo(() => {
    const counts = graph.nodes.reduce((accumulator, node) => ({ ...accumulator, [node.type]: (accumulator[node.type] || 0) + 1 }), {});
    return [
      { label: showAllEntities ? 'Entity overview' : 'Focused lens', value: showAllEntities ? `${entities.length} canonical companies` : selectedNode?.name || 'Choose a node', detail: showAllEntities ? 'Select a company to inspect its one-hop evidence' : selected ? `${showAllRelationships ? renderedEdges.length : neighborIds.size} ${showAllRelationships ? 'entity-scoped evidence relationships' : 'direct evidence relationships'}` : 'Start with a company, topic, or institution' },
      { label: 'Technology evidence', value: `${counts.research || 0} research · ${counts.patent || 0} patents`, detail: 'OpenAlex and USPTO-derived records' },
      { label: 'Public awards', value: `${counts.award || 0} awards · ${counts.recipient || 0} recipients`, detail: 'Bounded USAspending records' },
      { label: 'Canonical identity', value: `${counts.entity || 0} companies`, detail: 'SEC-derived identity records' },
    ];
  }, [graph, selectedNode, selected, neighborIds, renderedEdges, entities, showAllEntities, showAllRelationships]);

  const setDataMode = (nextMode) => {
    setMode(nextMode);
    if (nextMode === 'fixture') { setGraph(fixtureGraph); setApiState('idle'); setApiError(''); setSelected(defaultLens(fixtureGraph)?.id || null); setShowAllEntities(false); setShowAllRelationships(false); setExpandedTypes([]); setViewport({ x: 0, y: 0, scale: 1 }); }
  };

  const selectLens = (nodeId) => { setSelected(nodeId); setShowAllEntities(false); setShowAllRelationships(false); setExpandedTypes([]); setViewport({ x: 0, y: 0, scale: 1 }); };
  const toggleCluster = (type) => setExpandedTypes((current) => current.includes(type) ? current.filter((item) => item !== type) : [...current, type]);
  const zoomBy = (amount) => setViewport((current) => ({ ...current, scale: Math.max(0.6, Math.min(2.4, Number((current.scale + amount).toFixed(2)))) }));
  const panStart = (event) => { if (event.target.closest?.('.node')) return; panRef.current = { x: event.clientX, y: event.clientY, origin: viewport }; event.currentTarget.setPointerCapture?.(event.pointerId); };
  const panMove = (event) => { if (!panRef.current) return; const bounds = event.currentTarget.getBoundingClientRect(); const factor = 1120 / bounds.width / panRef.current.origin.scale; setViewport((current) => ({ ...current, x: panRef.current.origin.x + (event.clientX - panRef.current.x) * factor, y: panRef.current.origin.y + (event.clientY - panRef.current.y) * factor })); };
  const panEnd = () => { panRef.current = null; };

  const startStory = (storyId) => {
    setActiveStoryId(storyId);
    setStoryStep(0);
    setShowAllEntities(false);
    setShowAllRelationships(false);
    setStoryPickerOpen(false);
  };

  const exitStory = () => {
    setActiveStoryId(null);
    setStoryStep(0);
  };

  const advanceStory = () => {
    if (!activeStory) return;
    if (storyStep === activeStory.steps.length - 1) exitStory();
    else setStoryStep((current) => current + 1);
  };

  return (
    <div className="app-shell">
      <header className="topbar">
        <div>
          <div className="eyebrow">Investment Diligence Platform / Evidence Universe</div>
            <h1>Investment Diligence Knowledge Graph</h1>
          <p className="subtitle">{effectiveLive ? 'A live, read-only evidence graph spanning company identity, technology, public awards, and source lineage.' : 'A source-traceable fixture fallback is available whenever the live graph cannot be reached.'}</p>
        </div>
        <div className={`status ${effectiveLive ? 'live' : ''}`}><i /> {mode === 'postgres' ? apiState === 'loading' ? 'CONNECTING TO POSTGRES' : apiState === 'error' ? 'LIVE UNAVAILABLE · FIXTURE FALLBACK' : 'LIVE POSTGRES · READ ONLY' : 'FIXTURE MODE · SOURCE-TRACEABLE'}</div>
      </header>

      <nav className="toolbar" aria-label="Graph filters">
        {['all', '01', '02', '04', '05', 'sources'].map((option) => (
          <button key={option} className={filter === option ? 'active' : ''} onClick={() => setFilter(option)}>
            {option === 'all' ? 'All signals' : option === 'sources' ? 'Sources only' : `Pipeline ${option}`}
          </button>
        ))}
        <button onClick={() => { selectLens(defaultLens(graph)?.id || null); setShowAllEntities(false); setQuery(''); setFilter('all'); }}>Reset lens</button>
        <button className={showAllEntities ? 'active' : ''} onClick={() => { setShowAllEntities(true); setShowAllRelationships(false); setSelected(null); setExpandedTypes([]); setViewport({ x: 0, y: 0, scale: 1 }); }}>All entities</button>
        <label className="entity-filter">Company lens
          <select aria-label="Company lens" value={companyLensValue} onChange={(event) => {
            if (event.target.value === 'all') { setShowAllEntities(true); setShowAllRelationships(false); setSelected(null); setExpandedTypes([]); setViewport({ x: 0, y: 0, scale: 1 }); }
            else { selectLens(event.target.value); }
          }}>
            <option value="" disabled>Choose a company…</option>
            <option value="all">All canonical companies ({entities.length})</option>
            {entities.map((entity) => <option key={entity.id} value={entity.id}>{entity.name}</option>)}
          </select>
        </label>
        <button className={showAllRelationships ? 'active' : ''} disabled={!selected || showAllEntities} aria-pressed={showAllRelationships} onClick={() => setShowAllRelationships((current) => !current)}>{showAllRelationships ? 'Evidence: this entity' : 'Evidence: one hop'}</button>
        {!activeStory && <button className={`data-switch ${effectiveLive ? 'live-button' : ''}`} onClick={() => setDataMode(mode === 'postgres' ? 'fixture' : 'postgres')}>{effectiveLive ? '● Live data' : '○ Fixture fallback'}</button>}
        {activeStory && <span className={`demo-data-status ${effectiveLive ? 'live' : ''}`}>{effectiveLive ? '● Live evidence' : '○ Fixture fallback'}</span>}
        <button className={`demo-button ${activeStory ? 'active' : ''}`} onClick={() => setStoryPickerOpen((open) => !open)} aria-expanded={storyPickerOpen}>▶ Guided demo</button>
        <input value={query} onChange={(event) => setQuery(event.target.value)} className="search" type="search" placeholder="Search the evidence universe…" aria-label="Search graph nodes" />
      </nav>

      <section className="insight-row" aria-label="Graph insights">
        {metrics.map((metric) => <article className="insight-card" key={metric.label}><span>{metric.label}</span><strong>{metric.value}</strong><small>{metric.detail}</small></article>)}
      </section>

      <main className="stage">
        {storyPickerOpen && <StoryPicker stories={guidedStories} onStart={startStory} onClose={() => setStoryPickerOpen(false)} />}
        {activeStory && <StoryPresenter story={activeStory} step={storyStep} target={guidedTarget} onBack={() => setStoryStep((current) => Math.max(0, current - 1))} onNext={advanceStory} onExit={exitStory} />}
        {mode === 'postgres' && apiState !== 'ready' && <div className={`connection-banner ${apiState === 'error' ? 'error' : ''}`}><strong>{apiState === 'loading' ? 'Loading live PostgreSQL graph…' : 'Live PostgreSQL is unavailable'}</strong><span>{apiState === 'error' ? apiError : 'The fixture graph is intentionally hidden while live data is loading.'}</span></div>}
        <ClusterRail clusters={clusters} expandedTypes={expandedTypes} isOpen={clusterOpen} onToggleOpen={() => setClusterOpen((current) => !current)} position={clusterPosition} onPositionChange={setClusterPosition} onResetPosition={() => { setClusterPosition({ x: 330, y: 310 }); setClusterOpen(false); }} onToggle={toggleCluster} onCollapse={() => setExpandedTypes([])} />
        <div className="viewport-controls" aria-label="Graph zoom controls"><button onClick={() => zoomBy(-0.2)} aria-label="Zoom out">−</button><button onClick={() => setViewport({ x: 0, y: 0, scale: 1 })} aria-label="Reset graph view">◎</button><button onClick={() => zoomBy(0.2)} aria-label="Zoom in">+</button></div>
        <svg viewBox="0 0 1120 590" role="img" aria-label="Interactive investment diligence knowledge graph of source-backed evidence relationships" onWheel={(event) => { event.preventDefault(); zoomBy(event.deltaY > 0 ? -0.12 : 0.12); }} onPointerDown={panStart} onPointerMove={panMove} onPointerUp={panEnd} onPointerLeave={panEnd}>
          <defs><radialGradient id="core"><stop offset="0" stopColor="#8c7dff" stopOpacity=".32" /><stop offset="1" stopColor="#8c7dff" stopOpacity="0" /></radialGradient></defs>
          <g transform={`translate(${viewport.x} ${viewport.y}) translate(560 295) scale(${viewport.scale}) translate(-560 -295)`}>
            <g className="stars">{[[34,84],[115,260],[208,74],[333,506],[530,60],[693,514],[849,78],[1032,330],[1100,545]].map(([x, y]) => <circle key={`${x}-${y}`} cx={x} cy={y} r="1.3" />)}</g>
            <ellipse cx="555" cy="285" rx="390" ry="260" fill="url(#core)" />
            <Lane x="20" width="175" label="Sources" />
            <Lane x="215" width="175" label="Capture + identity" />
            <Lane x="410" width="205" label="Entities + recipients" />
            <Lane x="635" width="205" label="Research, patents + awards" />
            <Lane x="860" width="235" label="Evidence details" />
            <g className="edges">
            {renderedEdges.map((edge) => {
              const a = renderedNodeMap[edge.a]; const b = renderedNodeMap[edge.b];
              const connected = selected && (edge.a === selected || edge.b === selected);
              return <g key={`${edge.a}-${edge.b}`}>
                <line className={`edge ${edge.className || ''} ${connected ? 'highlight' : ''}`} x1={a.x} y1={a.y} x2={b.x} y2={b.y} />
                <text x={(a.x + b.x) / 2} y={(a.y + b.y) / 2 - 7} textAnchor="middle">{edge.label}</text>
              </g>;
            })}
            </g>
            <g className="nodes">
            {renderedNodes.map((node) => <Node key={node.id} node={node} selected={selected === node.id} guided={guidedTarget?.id === node.id} onSelect={selectLens} />)}
            </g>
          </g>
        </svg>
        <EvidencePanel node={selectedNode} graph={graph} nodeMap={nodeMap} entityOverview={showAllEntities} onOpenWorkspace={() => { setShowAllRelationships(true); setEvidenceWorkspaceOpen(true); }} />
        {evidenceWorkspaceOpen && selectedNode && <EvidenceWorkspace node={selectedNode} graph={graph} nodeMap={nodeMap} onClose={() => setEvidenceWorkspaceOpen(false)} onSelect={(nodeId) => { selectLens(nodeId); setEvidenceWorkspaceOpen(false); }} />}
      </main>

      <footer className="legend">
        <Legend color="var(--cyan)" label="Entity" /><Legend color="var(--violet)" label="Patent" /><Legend color="var(--orange)" label="Research work" /><Legend color="var(--green)" label="Institution" /><Legend color="#f2d45e" label="Public award" /><Legend color="var(--red)" label="Person" /><span className="reviewed-legend">Green edge = analyst-reviewed match</span><span className="candidate-legend">Dashed = candidate / unreviewed</span><span className="footer-note">{mode === 'postgres' ? 'PostgreSQL · read only' : 'Embedded fixture · not a production score'}</span>
      </footer>
    </div>
  );
}

function StoryPicker({ stories, onStart, onClose }) {
  return <section className="story-picker" role="dialog" aria-modal="true" aria-labelledby="story-picker-title">
    <div className="story-picker-heading"><div><div className="panel-title">Presenter mode</div><h2 id="story-picker-title">Choose a guided story</h2></div><button className="icon-button" onClick={onClose} aria-label="Close guided stories">×</button></div>
    <p>Each story focuses the live graph while keeping every claim tied to inspectable evidence.</p>
    <div className="story-list">{stories.map((story, index) => <button className="story-card" key={story.id} onClick={() => onStart(story.id)}><span className="story-number">0{index + 1}</span><span><small>{story.eyebrow}</small><strong>{story.title}</strong><em>{story.summary}</em></span><b aria-hidden="true">→</b></button>)}</div>
  </section>;
}

function StoryPresenter({ story, step, target, onBack, onNext, onExit }) {
  const current = story.steps[step];
  const isLast = step === story.steps.length - 1;
  return <section className="story-presenter" aria-live="polite">
    <div className="story-presenter-top"><div className="panel-title">{story.eyebrow}</div><button className="text-button" onClick={onExit}>Exit story</button></div>
    <div className="story-progress" aria-label={`Step ${step + 1} of ${story.steps.length}`}>{story.steps.map((item, index) => <i key={item.title} className={index <= step ? 'complete' : ''} />)}</div>
    <div className="story-count">Step {step + 1} of {story.steps.length}</div>
    <h2>{current.title}</h2>
    <p>{current.body}</p>
    <div className="story-target"><span>Focused evidence</span><strong>{target?.name || 'Waiting for available data'}</strong></div>
    <div className="story-actions"><button onClick={onBack} disabled={step === 0}>Back</button><button className="primary-action" onClick={onNext}>{isLast ? 'Finish story' : 'Next evidence'} <span aria-hidden="true">→</span></button></div>
  </section>;
}

function Lane({ x, width, label }) { return <><rect className="lane" x={x} y="38" width={width} height="510" rx="18" /><text className="lane-label" x={x + 20} y="68">{label}</text></>; }

function ClusterRail({ clusters, expandedTypes, isOpen, onToggleOpen, position, onPositionChange, onResetPosition, onToggle, onCollapse }) {
  const drag = useRef(null);
  if (!clusters.length && !expandedTypes.length) return null;
  const startDrag = (event) => {
    const stage = event.currentTarget.closest('.stage');
    if (!stage) return;
    drag.current = { stage, origin: position, startX: event.clientX, startY: event.clientY };
    event.currentTarget.setPointerCapture?.(event.pointerId);
  };
  const moveDrag = (event) => {
    if (!drag.current) return;
    const rail = event.currentTarget.closest('.cluster-rail');
    const stageBounds = drag.current.stage.getBoundingClientRect();
    const railBounds = rail.getBoundingClientRect();
    const x = Math.max(8, Math.min(stageBounds.width - railBounds.width - 8, drag.current.origin.x + event.clientX - drag.current.startX));
    const y = Math.max(8, Math.min(stageBounds.height - railBounds.height - 8, drag.current.origin.y + event.clientY - drag.current.startY));
    onPositionChange({ x, y });
  };
  const endDrag = () => { drag.current = null; };
  const clusterCount = clusters.length + expandedTypes.length;
  return <aside className={`cluster-rail ${isOpen ? 'open' : 'compact'}`} style={{ left: position.x, top: position.y }} aria-label="Collapsed evidence clusters"><div className="cluster-rail-header" onPointerDown={startDrag} onPointerMove={moveDrag} onPointerUp={endDrag} onPointerCancel={endDrag}><div><div className="panel-title">Collapsed evidence</div><span>{isOpen ? 'Drag to reposition. Expand a type to add it to this lens.' : `${clusterCount} evidence types · drag to reposition`}</span></div><div className="cluster-actions"><button className="icon-button cluster-toggle" onPointerDown={(event) => event.stopPropagation()} onClick={onToggleOpen} aria-expanded={isOpen}>{isOpen ? '−' : '+'}</button><button className="icon-button cluster-reset" onPointerDown={(event) => event.stopPropagation()} onClick={onResetPosition} aria-label="Reset collapsed evidence position">↺</button></div></div>{isOpen && <>{clusters.map((cluster) => <button key={cluster.type} onClick={() => onToggle(cluster.type)}><strong>{cluster.count}</strong> {cluster.type.replaceAll('_', ' ')} <b>+</b></button>)}{expandedTypes.length > 0 && <button className="collapse-button" onClick={onCollapse}>Collapse expanded records</button>}</>}</aside>;
}

function Node({ node, selected, guided, onSelect }) {
  const size = node.type === 'entity' ? 16 : node.type === 'source' ? 13 : 10;
  return <g className={`node ${node.type} ${selected ? 'selected' : ''} ${guided ? 'guided' : ''}`} onClick={(event) => { event.stopPropagation(); onSelect(node.id); }} tabIndex="0" role="button" aria-label={node.name} onKeyDown={(event) => (event.key === 'Enter' || event.key === ' ') && onSelect(node.id)}>
    {guided && <circle className="guided-ring" cx={node.x} cy={node.y} r={size + 12} />}
    <circle cx={node.x} cy={node.y} r={size} />
    <text x={node.x} y={node.y + size + 18} textAnchor="middle">{node.name}</text>
    <text className="kind" x={node.x} y={node.y + size + 33} textAnchor="middle">{node.kind}</text>
  </g>;
}

function EvidencePanel({ node, graph, nodeMap, entityOverview, onOpenWorkspace }) {
  if (!node) return <aside className="side-panel evidence-drawer"><div className="panel-title">Evidence drawer</div><div className="panel-name">{entityOverview ? 'All canonical companies' : 'Choose a lens'}</div><div className="panel-kind">{entityOverview ? 'Use the company lens control or select a visible company to inspect its one-hop evidence.' : 'Select a company, topic, or institution to focus the graph.'}</div><StatusBadge status={evidenceStatus(null)} /><div className="notice">{entityOverview ? 'This overview shows every loaded canonical entity. It does not imply a relationship among them.' : 'Collapsed clusters retain the scope of omitted evidence without presenting it as a relationship.'}</div></aside>;
  const status = evidenceStatus(node);
  const source = sourceFor(node, graph, nodeMap);
  const lineage = lineageFor(node, graph, nodeMap);
  const fields = Object.entries(node.fields || {}).filter(([key, value]) => value !== null && value !== undefined && value !== '' && !['run_id', 'source_record_id', 'content_sha256'].includes(key));
  const sourceLink = node.fields?.source_url || node.fields?.url || node.fields?.work_id?.startsWith('http') && node.fields.work_id || source?.fields?.source_uri;
  return <aside className="side-panel evidence-drawer"><div className="panel-title">Evidence drawer</div><div className="panel-name">{node.name}</div><div className="panel-kind">{node.kind}</div><StatusBadge status={status} /><p className="status-detail">{status.detail}</p><button className="open-workspace" onClick={onOpenWorkspace}>Open full entity evidence <span aria-hidden="true">↗</span></button><div className="lineage"><span>Lineage</span><strong>{lineage.join(' → ') || 'Source path unavailable'}</strong></div>{sourceLink && <a className="source-link" href={sourceLink} target="_blank" rel="noreferrer">Open original source <span aria-hidden="true">↗</span></a>}<dl>{fields.slice(0, 7).map(([key, value]) => <React.Fragment key={key}><dt>{fieldLabel(key)}</dt><dd>{typeof value === 'string' && /^https?:\/\//.test(value) ? <a href={value} target="_blank" rel="noreferrer">Open record ↗</a> : displayValue(key, value)}</dd></React.Fragment>)}</dl><div className={`notice ${status.tone === 'candidate' ? 'caution' : ''}`}>{status.tone === 'candidate' ? 'This item is discoverable evidence only. It cannot support a conclusion until analyst review.' : 'Source lineage is preserved through the original record, retrieval context, and evidence classification.'}</div></aside>;
}

function EvidenceWorkspace({ node, graph, nodeMap, onClose, onSelect }) {
  const paths = entityEvidencePathsFor(graph, node.id, nodeMap);
  const direct = paths.filter((item) => item.path.length === 2);
  return <section className="evidence-workspace" role="dialog" aria-modal="true" aria-labelledby="evidence-workspace-title"><div className="workspace-header"><div><div className="panel-title">Full entity evidence</div><h2 id="evidence-workspace-title">{node.name}</h2><p>{node.kind} · {paths.length} entity-linked records</p></div><button className="icon-button" onClick={onClose} aria-label="Close full entity evidence">×</button></div><div className="workspace-summary"><StatusBadge status={evidenceStatus(node)} /><span>Every path begins at this entity and stops at shared sources, people, institutions, or other companies. Green relationships have passed analyst review.</span></div><section className="workspace-section"><div className="workspace-section-heading"><h3>Direct relationships</h3><span>{direct.length}</span></div>{direct.length ? direct.map((item) => <ConnectionPath key={item.node.id} item={item} nodeMap={nodeMap} onSelect={onSelect} />) : <p className="empty-workspace">No direct relationships are loaded for this entity.</p>}</section><section className="workspace-section"><div className="workspace-section-heading"><h3>All evidence for this entity</h3><span>{paths.length}</span></div>{paths.length ? paths.map((item) => <ConnectionPath key={item.node.id} item={item} nodeMap={nodeMap} onSelect={onSelect} />) : <p className="empty-workspace">No entity-linked evidence is available.</p>}</section></section>;
}

function ConnectionPath({ item, nodeMap, onSelect }) {
  const pathNames = item.path.map((id) => nodeMap[id]?.name || id).join(' → ');
  return <button className="connection-path" onClick={() => onSelect(item.node.id)}><span className={`connection-type ${item.node.type}`}>{item.node.kind}</span><strong>{item.node.name}</strong><em>{pathNames}</em><small className={item.edge.className === 'reviewed' ? 'reviewed-copy' : ''}>{item.edge.className === 'reviewed' ? 'Analyst-reviewed match' : item.edge.label}</small></button>;
}

function StatusBadge({ status }) { return <div className={`status-badge ${status.tone}`}><i />{status.label}</div>; }

function Legend({ color, label }) { return <span><i style={{ background: color }} />{label}</span>; }

createRoot(document.getElementById('root')).render(<App />);
