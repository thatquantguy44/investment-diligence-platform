# Evidence-First Knowledge Graph UI & Style Specification

## Purpose

This specification describes a reusable interface for exploring a knowledge graph whose relationships have different evidence states. It is intended for diligence, research, intelligence, compliance, or investigation products where viewers must be able to distinguish source-backed facts from candidate matches and inferred signals.

The experience should feel like a polished analysis workspace rather than a generic graph visualizer. It should help someone answer three questions quickly:

1. What am I looking at?
2. What is directly supported by evidence?
3. What still needs human judgment?

## Design principles

- **Evidence before inference.** A visual connection must communicate whether it is source-derived, analyst-reviewed, candidate/unreviewed, inferred, or unavailable.
- **Focus before scale.** Start a person in a useful lens, show a one-hop neighborhood, and collapse everything else. A graph should not become an unreadable “hairball.”
- **Source paths are product features.** Every important object needs an inspectable path back to its source, retrieval context, and evidence classification.
- **Progressive disclosure.** Keep the first view clear; put dense metadata, graph-wide context, and action workflows behind purposeful controls.
- **Do not overclaim.** Labels, status language, and interaction copy must describe the scope of the record rather than imply commercial, ownership, performance, or causal conclusions not supported by data.

## Page structure

Use a dark, high-contrast workspace with this hierarchy:

```text
Header: product name, short evidence-focused subtitle, data-health indicator
Toolbar: pipeline filters, reset, lens selector, relationship scope, review toggle, search
Insight row: four compact cards that describe the current graph and evidence universe
Graph stage: graph canvas plus layered controls and drawers
Legend: node and edge semantics, source/data mode note
```

The graph stage is the visual anchor. Treat its overlays as workbench tools, not separate pages:

- left: optional guided narrative or review queue;
- right: evidence drawer for the selected object;
- center: full evidence workspace or decision modal when explicitly opened;
- movable: collapsed-evidence widget;
- lower right: zoom, pan reset, and other view controls.

Avoid permanent navigation rails. The product should feel like a focused analytical surface.

## Visual language

### Color and atmosphere

Use a deep navy/near-black background with a soft blue-violet radial glow behind the graph. The effect should be calm, technical, and legible—not a noisy “cyber” motif.

Recommended semantic palette:

| Meaning | Suggested treatment |
| --- | --- |
| Canonical entity / active interaction | bright cyan |
| Source / provenance path | muted cyan, dashed |
| Patent or structured technology record | violet |
| Research record | warm orange |
| Institution | green |
| Public award / financial detail | warm yellow |
| Person or cautionary signal | coral/red |
| Analyst-reviewed connection | bright green, solid, with a faint glow |
| Candidate / unreviewed connection | muted coral, dashed |
| Inferred relationship | restrained yellow, clearly labelled |
| Unavailable / unsupported | low-contrast gray-blue |

Use color as reinforcement, never as the only signal. Pair it with a label, stroke style, icon, badge, or explanatory copy.

### Typography

- Use an interface sans-serif such as Inter, system UI, or an equivalent modern neutral face.
- Use compact uppercase, letter-spaced labels for categories and panel eyebrows.
- Reserve large type for the product title and drawer/modal entity name.
- Keep graph labels brief; use the evidence drawer for long identifiers and fields.
- Favor plain-language labels: “Original record,” “Review status,” and “Retrieved” over database field names.

### Surfaces

Panels should use translucent dark fills, subtle 1px cool-toned borders, 14–20px corner radii, and soft large shadows. A small amount of backdrop blur can distinguish overlays from the graph without hiding it entirely.

Buttons are compact rounded pills in the toolbar and more rectangular, full-width actions inside drawers. Active state should use a brighter border and a restrained glow; it should not rely on a large solid fill.

## Graph model and visual semantics

### Node design

Each node has:

- a type-specific color and size;
- a concise name;
- a small second-line kind label;
- keyboard focus and click affordances;
- a selected state with a brighter border and glow.

Canonical entities should be visibly larger than records. Sources should look structurally different from entities, for example a darker fill with a colored outline.

### Edge design

Edges carry the relationship’s evidence classification:

- normal/source-derived: low-emphasis solid line;
- source provenance: cyan dashed line;
- candidate: coral dashed line;
- reviewed: green, slightly thicker line with a soft glow;
- selected-neighborhood relationship: cyan highlight over the semantic treatment.

Show a concise label at the edge midpoint only when the graph remains readable. It is acceptable to hide labels at low zoom or high density.

### Focused neighborhoods and clustering

The default lens is a selected company, person, institution, topic, or other anchor. Render its one-hop neighborhood by default. Offer a control to expand to all entity-scoped evidence paths.

Everything outside the lens should become a type-level cluster such as “119 patents” or “358 researchers,” rather than disappear without explanation. Clusters must:

- state count and type;
- be expandable individually;
- be collapsible again;
- be movable so they do not block source lanes or evidence drawers.

Always preserve a full-entity evidence view for an analyst who needs all paths touching the selected object. Stop traversal at shared hubs (for example, sources, people, institutions, or other canonical companies) so that a shared source does not pull the entire graph into the selected entity’s drawer.

## Interaction model

### Lens and filters

- Offer an **All entities** overview and a searchable entity/lens selector.
- Selecting an entity focuses its neighborhood and resets incidental expansion state.
- Offer a clear relationship-scope control: **one hop** versus **this entity’s evidence**.
- Keep pipeline/source filters visible but secondary to the lens.
- Provide reset, search, zoom, pan, and reset-view controls.

### Evidence drawer

The right-side drawer is the primary inspection surface. It should show:

- object name and kind;
- unmistakable evidence-status badge;
- plain-language status explanation;
- source lineage path;
- clickable original source link where available;
- selected, human-readable fields;
- an action to open the full scoped evidence workspace.

Candidate records must explicitly say that they require review and cannot support a conclusion yet. Reviewed records should name the fact that they passed analyst review, without implying more than the underlying evidence supports.

### Full evidence workspace

Open this only on demand. It should list direct relationships first, then all scoped evidence paths. Each row should show the related item, its type, its lineage, and review treatment. Selecting a row returns the person to that item’s scoped view.

## Review workflow

Candidate relationships are valuable, but should not pollute the default narrative. Make them opt-in with a **Review candidates** control.

When enabled:

- candidate edges become visible as dashed coral links;
- a side review queue shows candidates touching the selected lens;
- each candidate shows proposed canonical entity, source record, matching method, score, sector, and current review state;
- selecting a queue item opens the underlying source evidence;
- the evidence drawer provides a deliberate entry point to the decision workflow.

The review modal should:

- resolve the configured reviewer from the candidate’s sector on the server, not from browser input;
- allow approve, reject, and reopen actions;
- require a written note for approval and rejection;
- explain that the action appends an audit event rather than overwriting history;
- update the graph immediately after a successful decision.

Approved links move to green reviewed treatment. Rejected links leave the default graph but remain in a visible review-history area. Reopening returns a decision to the pending queue. Prevent a second accepted canonical match for the same source record until the existing accepted match is reopened or rejected.

## Data and API expectations

The UI should receive a graph payload with nodes, edges, and a review queue. Use stable IDs for every node, relationship, candidate, and source record.

At minimum, a candidate needs:

```json
{
  "candidateId": "stable-id",
  "sourceRecordId": "graph-node-id",
  "candidateEntityId": "canonical-entity-id",
  "sector": "sector-key",
  "matchScore": 0.0,
  "matchMethod": "method-name",
  "reviewStatus": "unreviewed | accepted | rejected",
  "reviewHistory": []
}
```

Review decisions should be append-only records containing action, previous state, reviewer, sector, note, timestamp, and decision ID. The graph should calculate its effective status from the latest decision while preserving history for audit.

## Accessibility and responsive behavior

- All graph nodes and controls must be keyboard reachable and have useful accessible names.
- Do not make hover the only way to discover status or actions.
- Respect reduced-motion preferences; disable decorative animated edge flow and focus pulses.
- On narrow screens, use a taller graph stage. Move the evidence drawer toward the bottom, keep review panels within the viewport, and make center modals full-width with comfortable margins.
- Keep contrast strong enough for low-light analyst environments. Do not use faint text for critical evidence status.

## Reuse checklist

For another repository, preserve the interaction and evidence rules while replacing domain-specific labels, node types, pipeline names, and source adapters.

- [ ] Define node and relationship evidence states before designing colors.
- [ ] Map those states to color, line style, label, and drawer copy.
- [ ] Identify the best default lens for the target users.
- [ ] Define shared hubs that stop full-evidence traversal.
- [ ] Supply lineage and original-source links for inspectable records.
- [ ] Make candidate relationships opt-in.
- [ ] Store review decisions append-only and resolve reviewer identity server-side.
- [ ] Keep filtering, focus, clustering, and review controls independent so users can compose them.
- [ ] Validate with both a sparse graph and a dense graph; the focus and clustering behavior should remain legible in both.

