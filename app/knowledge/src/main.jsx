import React, { useEffect, useMemo, useState } from 'react';
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

function App() {
  const [graph, setGraph] = useState(fixtureGraph);
  const [mode, setMode] = useState('fixture');
  const [apiState, setApiState] = useState('idle');
  const [apiError, setApiError] = useState('');
  const [filter, setFilter] = useState('all');
  const [query, setQuery] = useState('');
  const [selected, setSelected] = useState(null);
  const [storyPickerOpen, setStoryPickerOpen] = useState(false);
  const [activeStoryId, setActiveStoryId] = useState(null);
  const [storyStep, setStoryStep] = useState(0);
  const normalizedQuery = query.trim().toLowerCase();
  const nodeMap = useMemo(() => Object.fromEntries(graph.nodes.map((node) => [node.id, node])), [graph]);
  const selectedNode = selected ? nodeMap[selected] : null;
  const activeStory = guidedStories.find((story) => story.id === activeStoryId) || null;
  const activeStoryStep = activeStory?.steps[storyStep] || null;
  const guidedTarget = useMemo(() => activeStoryStep?.resolve(graph) || null, [activeStoryStep, graph]);

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
      .then((payload) => { if (!cancelled) { setGraph(payload); setApiState('ready'); setSelected(null); } })
      .catch((error) => { if (!cancelled) { setGraph(emptyGraph); setApiState('error'); setApiError(error.message || 'Start the local knowledge API and try again.'); } });
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

  const neighborIds = useMemo(() => {
    if (!selected) return new Set();
    return new Set(graph.edges.flatMap((edge) => {
      if (edge.a === selected) return [edge.b];
      if (edge.b === selected) return [edge.a];
      return [];
    }));
  }, [selected, graph]);

  const isDimmed = (node) => !visible(node) || (selected && node.id !== selected && !neighborIds.has(node.id));
  const isConnected = (edge) => selected && (edge.a === selected || edge.b === selected);

  const setDataMode = (nextMode) => {
    setMode(nextMode);
    if (nextMode === 'fixture') { setGraph(fixtureGraph); setApiState('idle'); setApiError(''); setSelected(null); }
  };

  const startStory = (storyId) => {
    setActiveStoryId(storyId);
    setStoryStep(0);
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
          <p className="subtitle">{mode === 'postgres' ? 'A live, read-only evidence graph spanning company identity, technology, public awards, and source lineage.' : 'A fixture-backed prototype of identity, technology, research, and lineage signals. Every visible relationship is inspectable.'}</p>
        </div>
        <div className={`status ${mode === 'postgres' && apiState === 'ready' ? 'live' : ''}`}><i /> {mode === 'postgres' ? apiState === 'loading' ? 'CONNECTING TO POSTGRES' : apiState === 'error' ? 'POSTGRES UNAVAILABLE' : 'LIVE POSTGRES · READ ONLY' : 'FIXTURE MODE · SOURCE-TRACEABLE'}</div>
      </header>

      <nav className="toolbar" aria-label="Graph filters">
        {['all', '01', '02', '04', '05', 'sources'].map((option) => (
          <button key={option} className={filter === option ? 'active' : ''} onClick={() => setFilter(option)}>
            {option === 'all' ? 'All signals' : option === 'sources' ? 'Sources only' : `Pipeline ${option}`}
          </button>
        ))}
        <button onClick={() => { setSelected(null); setQuery(''); setFilter('all'); }}>Reset focus</button>
        <span className="mode-label">Data:</span>
        <button className={mode === 'fixture' ? 'active' : ''} onClick={() => setDataMode('fixture')}>Embedded fixture</button>
        <button className={mode === 'postgres' ? 'active live-button' : ''} onClick={() => setDataMode('postgres')}>Live PostgreSQL</button>
        <button className={`demo-button ${activeStory ? 'active' : ''}`} onClick={() => setStoryPickerOpen((open) => !open)} aria-expanded={storyPickerOpen}>▶ Guided demo</button>
        <input value={query} onChange={(event) => setQuery(event.target.value)} className="search" type="search" placeholder="Search the evidence universe…" aria-label="Search graph nodes" />
      </nav>

      <main className="stage">
        {storyPickerOpen && <StoryPicker stories={guidedStories} onStart={startStory} onClose={() => setStoryPickerOpen(false)} />}
        {activeStory && <StoryPresenter story={activeStory} step={storyStep} target={guidedTarget} onBack={() => setStoryStep((current) => Math.max(0, current - 1))} onNext={advanceStory} onExit={exitStory} />}
        {mode === 'postgres' && apiState !== 'ready' && <div className={`connection-banner ${apiState === 'error' ? 'error' : ''}`}><strong>{apiState === 'loading' ? 'Loading live PostgreSQL graph…' : 'Live PostgreSQL is unavailable'}</strong><span>{apiState === 'error' ? apiError : 'The fixture graph is intentionally hidden while live data is loading.'}</span></div>}
        <svg viewBox="0 0 1120 590" role="img" aria-label="Interactive investment diligence knowledge graph of source-backed evidence relationships">
          <defs><radialGradient id="core"><stop offset="0" stopColor="#8c7dff" stopOpacity=".32" /><stop offset="1" stopColor="#8c7dff" stopOpacity="0" /></radialGradient></defs>
          <g className="stars">{[[34,84],[115,260],[208,74],[333,506],[530,60],[693,514],[849,78],[1032,330],[1100,545]].map(([x, y]) => <circle key={`${x}-${y}`} cx={x} cy={y} r="1.3" />)}</g>
          <ellipse cx="555" cy="285" rx="390" ry="260" fill="url(#core)" />
          <Lane x="20" width="175" label="Sources" />
          <Lane x="215" width="175" label="Capture + identity" />
          <Lane x="410" width="205" label="Entities + recipients" />
          <Lane x="635" width="205" label="Research, patents + awards" />
          <Lane x="860" width="235" label="Evidence details" />
          <g className="edges">
            {graph.edges.map((edge) => {
              const a = nodeMap[edge.a]; const b = nodeMap[edge.b];
              const dimmed = selected ? !isConnected(edge) : !visible(a) || !visible(b);
              return <g key={`${edge.a}-${edge.b}`} className={dimmed ? 'dim' : ''}>
                <line className={`edge ${edge.className || ''} ${isConnected(edge) ? 'highlight' : ''}`} x1={a.x} y1={a.y} x2={b.x} y2={b.y} />
                <text x={(a.x + b.x) / 2} y={(a.y + b.y) / 2 - 7} textAnchor="middle">{edge.label}</text>
              </g>;
            })}
          </g>
          <g className="nodes">
            {graph.nodes.map((node) => <Node key={node.id} node={node} dimmed={isDimmed(node)} selected={selected === node.id} guided={guidedTarget?.id === node.id} onSelect={setSelected} />)}
          </g>
        </svg>
        <EvidencePanel node={selectedNode} />
      </main>

      <footer className="legend">
        <Legend color="var(--cyan)" label="Entity" /><Legend color="var(--violet)" label="Patent" /><Legend color="var(--orange)" label="Research work" /><Legend color="var(--green)" label="Institution" /><Legend color="#f2d45e" label="Public award" /><Legend color="var(--red)" label="Person" /><span className="candidate-legend">Dashed = candidate / unreviewed</span><span className="footer-note">{mode === 'postgres' ? 'PostgreSQL · read only' : 'Embedded fixture · not a production score'}</span>
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

function Node({ node, dimmed, selected, guided, onSelect }) {
  const size = node.type === 'entity' ? 16 : node.type === 'source' ? 13 : 10;
  return <g className={`node ${node.type} ${dimmed ? 'dim' : ''} ${selected ? 'selected' : ''} ${guided ? 'guided' : ''}`} onClick={() => onSelect(node.id)} tabIndex="0" role="button" aria-label={node.name} onKeyDown={(event) => (event.key === 'Enter' || event.key === ' ') && onSelect(node.id)}>
    {guided && <circle className="guided-ring" cx={node.x} cy={node.y} r={size + 12} />}
    <circle cx={node.x} cy={node.y} r={size} />
    <text x={node.x} y={node.y + size + 18} textAnchor="middle">{node.name}</text>
    <text className="kind" x={node.x} y={node.y + size + 33} textAnchor="middle">{node.kind}</text>
  </g>;
}

function EvidencePanel({ node }) {
  if (!node) return <aside className="side-panel"><div className="panel-title">Selected evidence</div><div className="panel-name">Select a node</div><div className="panel-kind">The graph will isolate its evidence neighborhood.</div><div className="notice">Dashed edges indicate candidate or unreviewed relationships. They are not confirmations of ownership or employment.</div></aside>;
  const caution = node.type === 'person' || node.id === 'energy';
  return <aside className="side-panel"><div className="panel-title">Selected evidence</div><div className="panel-name">{node.name}</div><div className="panel-kind">{node.kind}</div><dl>{Object.entries(node.fields).map(([key, value]) => <React.Fragment key={key}><dt>{key}</dt><dd>{value}</dd></React.Fragment>)}</dl><div className={`notice ${caution ? 'caution' : ''}`}>{caution ? 'Caution: this is source evidence only. It does not confirm employment, ownership, control, or technology quality.' : 'Lineage is preserved through the source record, adapter version, retrieval status, and content hash.'}</div></aside>;
}

function Legend({ color, label }) { return <span><i style={{ background: color }} />{label}</span>; }

createRoot(document.getElementById('root')).render(<App />);
