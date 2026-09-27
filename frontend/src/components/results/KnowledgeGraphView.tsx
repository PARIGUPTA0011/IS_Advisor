import { useMemo, useState } from "react";
import { Network } from "lucide-react";
import type { KnowledgeGraphEdge, KnowledgeGraphNode, Relationship } from "../../types/api";

interface Props {
  nodes: KnowledgeGraphNode[];
  edges: KnowledgeGraphEdge[];
}

// How each relationship reads and is drawn, and whether it is shown before the
// user asks. Normative references (clause 2) and replacements answer "what else
// must I comply with / what supersedes this"; the scraped cross-references are
// numerous and noisy, so "cited by" (often hundreds) starts hidden; what a
// standard itself cites stays on, since that is what applies alongside it.
const RELATIONS: Record<Relationship, { label: string; color: string; dash?: string; on: boolean }> = {
  NORMATIVELY_REFERENCES: { label: "Normative reference", color: "var(--accent-primary)", on: true },
  REPLACED_BY: { label: "Replaced by", color: "var(--status-warning)", dash: "7 5", on: true },
  REPLACES: { label: "Supersedes", color: "var(--status-warning)", dash: "7 5", on: true },
  REFERENCES: { label: "Cites", color: "var(--status-current)", dash: "2 4", on: true },
  REFERENCED_BY: { label: "Cited by", color: "var(--text-muted)", dash: "2 4", on: false },
};
const ORDER = Object.keys(RELATIONS) as Relationship[];

// Geometry of the drawing, in SVG units; the viewBox scales it to any width.
const W = 820;
const H = 480;
const CX = W / 2;
const CY = H / 2;
const CENTER_R = 72;
const NODE_R = 42;
const RING_X = 305;   // the ring is an ellipse, to use the wide panel
const RING_Y = 170;
const MAX_NEIGHBOURS = 12; // past this the ring crowds; the rest are counted

interface Neighbour {
  node: KnowledgeGraphNode;
  relationship: Relationship;
  x: number;
  y: number;
}

// "Hot rolled medium and high tensile structural steel - Specification" ->
// "Hot rolled medium and high…": the phrase before any " - " or ":" part,
// trimmed to fit a circle.
function shortTitle(title: string | null, max: number): string {
  if (!title) return "";
  let text = title.replace(/^(specification|code of practice|method[s]? of test)\s+for\s+/i, "");
  text = text.split(/\s[-–—]\s|:\s/)[0].trim();
  text = text.charAt(0).toUpperCase() + text.slice(1);
  return text.length > max ? `${text.slice(0, max - 1).trimEnd()}…` : text;
}

// "IS 3803 (Part 1) (Sec 2):2019" -> base "IS 3803", part "(Part 1) (Sec 2)":
// two lines, so a long number fits inside its circle.
function splitNumber(id: string): { base: string; part: string } {
  const bare = id.replace(/:\d{4}$/, "");
  const at = bare.indexOf(" (");
  return at === -1 ? { base: bare, part: "" } : { base: bare.slice(0, at), part: bare.slice(at + 1) };
}

// Shrink a label's font until its estimated width fits; SVG text does not
// wrap, and an IS/ISO number can be twice as long as a plain one.
function fitFont(text: string, size: number, maxWidth: number): number {
  const estimated = text.length * size * 0.6;
  return estimated <= maxWidth ? size : Math.max(8, (size * maxWidth) / estimated);
}

// Where a line between two circles should start and end: on their edges, not
// their centres, so it never runs under the text.
function edgePoints(x2: number, y2: number, r2: number) {
  const dx = x2 - CX;
  const dy = y2 - CY;
  const length = Math.hypot(dx, dy) || 1;
  return {
    x1: CX + (dx / length) * CENTER_R,
    y1: CY + (dy / length) * CENTER_R,
    x2: x2 - (dx / length) * r2,
    y2: y2 - (dy / length) * r2,
  };
}

export function KnowledgeGraphView({ nodes, edges }: Props) {
  const retrieved = useMemo(() => nodes.filter((n) => n.retrieved), [nodes]);
  const nodeById = useMemo(() => new Map(nodes.map((n) => [n.id, n])), [nodes]);

  const [focusId, setFocusId] = useState<string | null>(null);
  const focus = retrieved.find((n) => n.id === focusId) ?? retrieved[0] ?? null;
  const [enabled, setEnabled] = useState<Record<string, boolean>>(
    () => Object.fromEntries(ORDER.map((r) => [r, RELATIONS[r].on])),
  );
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [hoverId, setHoverId] = useState<string | null>(null);

  // Every relationship of the focus standard, one entry per neighbour and type.
  const byType = useMemo(() => {
    const groups: Partial<Record<Relationship, KnowledgeGraphNode[]>> = {};
    if (!focus) return groups;
    for (const edge of edges) {
      if (edge.source !== focus.id && edge.target !== focus.id) continue;
      const other = nodeById.get(edge.source === focus.id ? edge.target : edge.source);
      if (!other || other.id === focus.id) continue;
      const list = (groups[edge.relationship] ??= []);
      if (!list.some((n) => n.id === other.id)) list.push(other);
    }
    for (const list of Object.values(groups)) {
      list?.sort((a, b) => a.standard_id.localeCompare(b.standard_id, undefined, { numeric: true }));
    }
    return groups;
  }, [edges, focus, nodeById]);

  // Only standards with an enabled relationship to the focus are placed, in
  // relationship order, evenly around the ring starting at the top.
  const { neighbours, overflow } = useMemo(() => {
    const picked: { node: KnowledgeGraphNode; relationship: Relationship }[] = [];
    const seen = new Set<string>();
    let total = 0;
    for (const relationship of ORDER) {
      if (!enabled[relationship]) continue;
      for (const node of byType[relationship] ?? []) {
        if (seen.has(node.id)) continue;
        seen.add(node.id);
        total += 1;
        if (picked.length < MAX_NEIGHBOURS) picked.push({ node, relationship });
      }
    }
    const placed: Neighbour[] = picked.map((entry, index) => {
      const angle = -Math.PI / 2 + (2 * Math.PI * index) / Math.max(picked.length, 1);
      return { ...entry, x: CX + RING_X * Math.cos(angle), y: CY + RING_Y * Math.sin(angle) };
    });
    return { neighbours: placed, overflow: total - picked.length };
  }, [byType, enabled]);

  const selected = selectedId ? nodeById.get(selectedId) ?? null : null;
  const selectedRelation = neighbours.find((n) => n.node.id === selectedId)?.relationship;

  return (
    <section className="glass-panel overflow-hidden rounded-2xl">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border px-5 py-4">
        <div className="flex items-center gap-3">
          <span className="flex size-9 items-center justify-center rounded-lg bg-accent-gold-soft text-accent-gold">
            <Network size={18} />
          </span>
          <div>
            <h2 className="text-sm font-semibold text-text-primary">Knowledge graph</h2>
            <p className="text-xs text-text-muted">
              Select a standard to trace what it requires, what it replaced, and what replaced it
            </p>
          </div>
        </div>
        {focus && overflow > 0 && (
          <span className="text-xs text-text-muted">+{overflow} more not drawn (limit {MAX_NEIGHBOURS})</span>
        )}
      </div>

      {!focus ? (
        <div className="flex min-h-56 flex-col items-center justify-center px-6 text-center">
          <Network size={24} className="text-text-muted" />
          <p className="mt-3 text-sm font-medium text-text-primary">No graph relationships found</p>
          <p className="mt-1 max-w-sm text-xs text-text-muted">
            None of the recommended standards has recorded relationships in the knowledge graph.
          </p>
        </div>
      ) : (
        <>
          {retrieved.length > 1 && (
            <div className="flex flex-wrap gap-2 border-b border-border px-5 py-3">
              {retrieved.map((node) => (
                <button
                  key={node.id}
                  type="button"
                  title={node.title ?? undefined}
                  onClick={() => {
                    setFocusId(node.id);
                    setSelectedId(null);
                  }}
                  className={`rounded-full border px-3 py-1 text-xs font-medium transition-colors ${
                    node.id === focus.id
                      ? "border-[var(--accent-primary)] bg-[var(--accent-primary)] text-[var(--text-on-primary)]"
                      : "border-border text-text-secondary hover:border-[var(--accent-primary)]"
                  }`}
                >
                  {node.standard_id}
                </button>
              ))}
            </div>
          )}

          <div className="flex flex-wrap gap-2 px-5 pt-3">
            {ORDER.map((relationship) => {
              const count = byType[relationship]?.length ?? 0;
              const style = RELATIONS[relationship];
              const on = enabled[relationship];
              return (
                <button
                  key={relationship}
                  type="button"
                  disabled={count === 0}
                  aria-pressed={on}
                  onClick={() => setEnabled((prev) => ({ ...prev, [relationship]: !prev[relationship] }))}
                  className={`inline-flex items-center gap-2 rounded-lg border border-border px-2.5 py-1 text-xs text-text-secondary transition-opacity ${
                    count === 0 ? "cursor-not-allowed opacity-35" : on ? "opacity-100" : "opacity-50"
                  }`}
                >
                  <svg width="18" height="4" aria-hidden="true">
                    <line x1="0" y1="2" x2="18" y2="2" stroke={style.color} strokeWidth="2" strokeDasharray={style.dash} />
                  </svg>
                  {style.label}
                  <span className="font-semibold text-text-primary">{count}</span>
                </button>
              );
            })}
          </div>

          <svg
            viewBox={`0 0 ${W} ${H}`}
            className="block h-auto w-full"
            role="img"
            aria-label={`Relationships of ${focus.standard_id}`}
            onClick={() => setSelectedId(null)}
          >
            <defs>
              <radialGradient id="kg-center" cx="40%" cy="35%" r="75%">
                <stop offset="0%" stopColor="var(--accent-primary)" stopOpacity="0.85" />
                <stop offset="100%" stopColor="var(--accent-primary)" />
              </radialGradient>
            </defs>

            {neighbours.map(({ node, relationship, x, y }) => {
              const style = RELATIONS[relationship];
              const p = edgePoints(x, y, NODE_R);
              const dim = hoverId !== null && hoverId !== node.id;
              return (
                <line
                  key={`edge-${node.id}`}
                  {...p}
                  stroke={style.color}
                  strokeWidth={hoverId === node.id || selectedId === node.id ? 3 : 2}
                  strokeDasharray={style.dash}
                  strokeLinecap="round"
                  opacity={dim ? 0.25 : 0.9}
                >
                  <title>{`${focus.standard_id} — ${style.label} — ${node.standard_id}`}</title>
                </line>
              );
            })}

            {neighbours.map(({ node, relationship, x, y }) => {
              const withdrawn = node.status === "withdrawn";
              const isSelected = selectedId === node.id;
              const dim = hoverId !== null && hoverId !== node.id;
              return (
                <g
                  key={`node-${node.id}`}
                  transform={`translate(${x} ${y})`}
                  className="cursor-pointer"
                  opacity={dim ? 0.45 : 1}
                  onMouseEnter={() => setHoverId(node.id)}
                  onMouseLeave={() => setHoverId(null)}
                  onClick={(event) => {
                    event.stopPropagation();
                    setSelectedId(node.id);
                  }}
                >
                  <title>{`${node.standard_id}${node.title ? ` — ${node.title}` : ""}`}</title>
                  <circle
                    r={NODE_R}
                    fill="var(--surface)"
                    stroke={withdrawn ? "var(--status-withdrawn)" : RELATIONS[relationship].color}
                    strokeOpacity={isSelected ? 1 : 0.55}
                    strokeWidth={isSelected ? 3 : 1.5}
                  />
                  {(() => {
                    const { base, part } = splitNumber(node.standard_id);
                    return (
                      <>
                        <text y={part ? -11 : -5} textAnchor="middle" fontSize={fitFont(base, 12.5, NODE_R * 1.7)}
                              fontWeight="700" fill="var(--text-primary)">
                          {base}
                        </text>
                        {part && (
                          <text y={2} textAnchor="middle" fontSize={fitFont(part, 10, NODE_R * 1.7)}
                                fontWeight="600" fill="var(--text-primary)">
                            {part}
                          </text>
                        )}
                        <text y={part ? 16 : 12} textAnchor="middle" fontSize="9.5"
                              fill={withdrawn ? "var(--status-withdrawn)" : "var(--text-secondary)"}>
                          {withdrawn ? "Withdrawn" : shortTitle(node.title, part ? 14 : 16)}
                        </text>
                      </>
                    );
                  })()}
                </g>
              );
            })}

            <g transform={`translate(${CX} ${CY})`}>
              <title>{`${focus.standard_id}${focus.title ? ` — ${focus.title}` : ""}`}</title>
              <circle r={CENTER_R + 10} fill="var(--accent-primary)" opacity="0.12" />
              <circle r={CENTER_R} fill="url(#kg-center)" />
              <text y={-6} textAnchor="middle" fontSize="16" fontWeight="700" fill="var(--text-on-primary)">
                {focus.standard_id.replace(/:\d{4}$/, "")}
              </text>
              <text y={14} textAnchor="middle" fontSize="11" fill="var(--text-on-primary)" opacity="0.9">
                {shortTitle(focus.title, 20)}
              </text>
            </g>

            {neighbours.length === 0 && (
              <text x={CX} y={CY + CENTER_R + 36} textAnchor="middle" fontSize="12" fill="var(--text-muted)">
                No relationships of the selected types — turn on another type above
              </text>
            )}
          </svg>

          <div className="border-t border-border px-5 py-3 text-xs text-text-secondary">
            {selected ? (
              <div>
                <div className="flex flex-wrap items-baseline gap-x-2 gap-y-1">
                  <strong className="text-sm text-text-primary">{selected.standard_id}</strong>
                  {selectedRelation && (
                    <span className="text-text-muted">
                      {RELATIONS[selectedRelation].label.toLowerCase()} of {focus.standard_id}
                    </span>
                  )}
                  {selected.status === "withdrawn" && (
                    <span className="font-medium text-[var(--status-withdrawn)]">Withdrawn</span>
                  )}
                </div>
                {selected.title && <p className="mt-1 text-sm text-text-secondary">{selected.title}</p>}
                {selected.retrieved && selected.id !== focus.id && (
                  <button
                    type="button"
                    className="mt-2 text-xs font-medium text-[var(--accent-primary)] hover:underline"
                    onClick={() => {
                      setFocusId(selected.id);
                      setSelectedId(null);
                    }}
                  >
                    Centre the graph on {selected.standard_id}
                  </button>
                )}
              </div>
            ) : (
              <span className="text-text-muted">
                Hover to highlight a relationship · click a standard for its full title
              </span>
            )}
          </div>
        </>
      )}
    </section>
  );
}
