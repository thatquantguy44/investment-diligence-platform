import React, { useMemo, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { graph } from './data';
import './styles.css';

const nodeMap = Object.fromEntries(graph.nodes.map((node) => [node.id, node]));

function App() {
  const [filter, setFilter] = useState('all');
  const [query, setQuery] = useState('');
  const [selected, setSelected] = useState(null);
  const selectedNode = selected ? nodeMap[selected] : null;
  const normalizedQuery = query.trim().toLowerCase();

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
  }, [selected]);

  const isDimmed = (node) => !visible(node) || (selected && node.id !== selected && !neighborIds.has(node.id));
  const isConnected = (edge) => selected && (edge.a === selected || edge.b === selected);

  return (
    <div className="app-shell">
      <header className="topbar">
        <div>
          <div className="eyebrow">Investment Diligence Platform / Evidence Universe</div>
          <h1>Pipeline 01 + 02 Knowledge Graph</h1>
          <p className="subtitle">A fixture-backed prototype of identity, technology, research, and lineage signals. Every visible relationship is inspectable.</p>
        </div>
        <div className="status"><i /> PILOT MODE · SOURCE-TRACEABLE</div>
      </header>

      <nav className="toolbar" aria-label="Graph filters">
        {['all', '01', '02', 'sources'].map((option) => (
          <button key={option} className={filter === option ? 'active' : ''} onClick={() => setFilter(option)}>
            {option === 'all' ? 'All signals' : option === 'sources' ? 'Sources only' : `Pipeline ${option}`}
          </button>
        ))}
        <button onClick={() => { setSelected(null); setQuery(''); setFilter('all'); }}>Reset focus</button>
        <input value={query} onChange={(event) => setQuery(event.target.value)} className="search" type="search" placeholder="Search the evidence universe…" aria-label="Search graph nodes" />
      </nav>

      <main className="stage">
        <svg viewBox="0 0 1120 590" role="img" aria-label="Interactive knowledge graph of Pipeline 01 and Pipeline 02 evidence relationships">
          <defs><radialGradient id="core"><stop offset="0" stopColor="#8c7dff" stopOpacity=".32" /><stop offset="1" stopColor="#8c7dff" stopOpacity="0" /></radialGradient></defs>
          <g className="stars">{[[34,84],[115,260],[208,74],[333,506],[530,60],[693,514],[849,78],[1032,330],[1100,545]].map(([x, y]) => <circle key={`${x}-${y}`} cx={x} cy={y} r="1.3" />)}</g>
          <ellipse cx="555" cy="285" rx="390" ry="260" fill="url(#core)" />
          <Lane x="20" width="175" label="01 · Sources" />
          <Lane x="215" width="175" label="Capture + identity" />
          <Lane x="410" width="205" label="Canonical graph" />
          <Lane x="635" width="205" label="02 · Signals" />
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
            {graph.nodes.map((node) => <Node key={node.id} node={node} dimmed={isDimmed(node)} selected={selected === node.id} onSelect={setSelected} />)}
          </g>
        </svg>
        <EvidencePanel node={selectedNode} />
      </main>

      <footer className="legend">
        <Legend color="var(--cyan)" label="Entity" /><Legend color="var(--violet)" label="Patent" /><Legend color="var(--orange)" label="Research work" /><Legend color="var(--green)" label="Institution" /><Legend color="var(--red)" label="Person" /><span className="candidate-legend">Dashed = candidate / unreviewed</span><span className="footer-note">Fixture-backed pilot · not a production score</span>
      </footer>
    </div>
  );
}

function Lane({ x, width, label }) { return <><rect className="lane" x={x} y="38" width={width} height="510" rx="18" /><text className="lane-label" x={x + 20} y="68">{label}</text></>; }

function Node({ node, dimmed, selected, onSelect }) {
  const size = node.type === 'entity' ? 16 : node.type === 'source' ? 13 : 10;
  return <g className={`node ${node.type} ${dimmed ? 'dim' : ''} ${selected ? 'selected' : ''}`} onClick={() => onSelect(node.id)} tabIndex="0" role="button" aria-label={node.name} onKeyDown={(event) => (event.key === 'Enter' || event.key === ' ') && onSelect(node.id)}>
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
