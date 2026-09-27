import { useEffect, useMemo, useRef, useState } from "react";
import ForceGraph2D, { type ForceGraphMethods } from "react-force-graph-2d";
import { Network } from "lucide-react";
import type { KnowledgeGraphEdge, KnowledgeGraphNode, Relationship } from "../../types/api";

interface Props {
  nodes: KnowledgeGraphNode[];
  edges: KnowledgeGraphEdge[];
}

interface GraphNode extends KnowledgeGraphNode {
  x?: number;
  y?: number;
  fx?: number;
  fy?: number;
  isFocus?: boolean;
}

interface GraphLink extends Omit<KnowledgeGraphEdge, "source" | "target"> {
  source: string | GraphNode;
  target: string | GraphNode;
}

// One entry per relationship type: how it reads, how it is drawn, and whether
// it is shown before the user asks. Normative references (clause 2) and
// replacements answer "what else must I comply with / what supersedes this";
// the scraped cross-references are numerous and noisy, so they start hidden.
const RELATIONS: Record<Relationship, { label: string; color: string; dash: number[] | null; on: boolean }> = {
  NORMATIVELY_REFERENCES: { label: "Normative references", color: "#6d4bd1", dash: null, on: true },
  REPLACED_BY: { label: "Replaced by", color: "#cf7938", dash: null, on: true },
  REPLACES: { label: "Supersedes", color: "#cf7938", dash: null, on: true },
  REFERENCES: { label: "Cites", color: "#287c70", dash: [5, 4], on: false },
  REFERENCED_BY: { label: "Cited by", color: "#8a949e", dash: [2, 3], on: false },
};
const ORDER = Object.keys(RELATIONS) as Relationship[];

// A standard like IS 1786 is cited by dozens of others; past this many
// neighbours per relationship the drawing stops being readable.
const MAX_PER_RELATION = 10;
const HEIGHT = 440;

export function KnowledgeGraphView({ nodes, edges }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const graphRef = useRef<ForceGraphMethods<GraphNode, GraphLink> | undefined>(undefined);
  const [width, setWidth] = useState(720);
  const [selected, setSelected] = useState<KnowledgeGraphNode | null>(null);

  const retrieved = useMemo(() => nodes.filter((n) => n.retrieved), [nodes]);
  const [focusId, setFocusId] = useState<string | null>(null);
  const focus = retrieved.find((n) => n.id === focusId) ?? retrieved[0] ?? null;

  const [enabled, setEnabled] = useState<Record<string, boolean>>(
    () => Object.fromEntries(ORDER.map((r) => [r, RELATIONS[r].on])),
  );

  // Edges touching the focus standard, grouped by type, before any filtering:
  // the counts on the filter chips come from here.
  const byType = useMemo(() => {
    const groups: Partial<Record<Relationship, KnowledgeGraphEdge[]>> = {};
    if (!focus) return groups;
    for (const edge of edges) {
      if (edge.source !== focus.id && edge.target !== focus.id) continue;
      (groups[edge.relationship] ??= []).push(edge);
    }
    return groups;
  }, [edges, focus]);

  const nodeById = useMemo(() => new Map(nodes.map((n) => [n.id, n])), [nodes]);

  const { graphData, hidden } = useMemo(() => {
    if (!focus) return { graphData: { nodes: [], links: [] }, hidden: 0 };
    const keep = new Map<string, GraphNode>([[focus.id, { ...focus, isFocus: true, fx: 0, fy: 0 }]]);
    const links: GraphLink[] = [];
    let dropped = 0;
    for (const relation of ORDER) {
      const group = byType[relation] ?? [];
      if (!enabled[relation]) continue;
      group.forEach((edge, index) => {
        if (index >= MAX_PER_RELATION) {
          dropped += 1;
          return;
        }
        const otherId = edge.source === focus.id ? edge.target : edge.source;
        const other = nodeById.get(otherId);
        if (!other) return;
        if (!keep.has(otherId)) keep.set(otherId, { ...other });
        links.push({ ...edge });
      });
    }
    return { graphData: { nodes: [...keep.values()], links }, hidden: dropped };
  }, [byType, enabled, focus, nodeById]);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;
    const observer = new ResizeObserver(([entry]) => setWidth(Math.floor(entry.contentRect.width)));
    observer.observe(container);
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    graphRef.current?.d3Force("link")?.distance(90);
    graphRef.current?.d3Force("charge")?.strength(-260);
  }, [graphData]);

  const shown = graphData.links.length;

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
              What each recommended standard depends on and what it replaced
            </p>
          </div>
        </div>
        {focus && (
          <div className="text-xs text-text-secondary">
            {shown} of {Object.values(byType).reduce((sum, g) => sum + (g?.length ?? 0), 0)} relationships shown
            {hidden > 0 && <span className="text-text-muted"> · {hidden} more hidden (limit {MAX_PER_RELATION} per type)</span>}
          </div>
        )}
      </div>

      {!focus ? (
        <div className="flex min-h-56 flex-col items-center justify-center px-6 text-center">
          <Network size={24} className="text-text-muted" />
          <p className="mt-3 text-sm font-medium text-text-primary">No graph relationships found</p>
          <p className="mt-1 max-w-sm text-xs text-text-muted">
            This analysis did not retrieve standards with connected knowledge-graph relationships.
          </p>
        </div>
      ) : (
        <>
          {/* Which recommended standard sits at the centre. */}
          {retrieved.length > 1 && (
            <div className="flex flex-wrap gap-2 border-b border-border px-5 py-3">
              {retrieved.map((node) => (
                <button
                  key={node.id}
                  type="button"
                  onClick={() => {
                    setFocusId(node.id);
                    setSelected(null);
                  }}
                  title={node.title ?? undefined}
                  className={`rounded-full border px-3 py-1 text-xs font-medium transition-colors ${
                    node.id === focus.id
                      ? "border-[#1678d2] bg-[#1678d2] text-white"
                      : "border-border text-text-secondary hover:border-[#1678d2]"
                  }`}
                >
                  {node.standard_id}
                </button>
              ))}
            </div>
          )}

          {/* Relationship filters, with how many of each the focus standard has. */}
          <div className="flex flex-wrap gap-2 px-5 py-3">
            {ORDER.map((relation) => {
              const count = byType[relation]?.length ?? 0;
              const style = RELATIONS[relation];
              const on = enabled[relation];
              return (
                <button
                  key={relation}
                  type="button"
                  disabled={count === 0}
                  onClick={() => setEnabled((prev) => ({ ...prev, [relation]: !prev[relation] }))}
                  className={`inline-flex items-center gap-2 rounded-lg border px-2.5 py-1 text-xs transition-opacity ${
                    count === 0 ? "cursor-not-allowed opacity-40" : on ? "opacity-100" : "opacity-55"
                  } border-border text-text-secondary`}
                  aria-pressed={on}
                >
                  <i
                    className="h-0.5 w-4"
                    style={{
                      borderTop: `2px ${style.dash ? "dashed" : "solid"} ${style.color}`,
                    }}
                  />
                  {style.label}
                  <span className="font-semibold text-text-primary">{count}</span>
                </button>
              );
            })}
          </div>

          <div ref={containerRef} className="w-full bg-[var(--bg-elevated)]" style={{ height: HEIGHT }}>
            <ForceGraph2D
              ref={graphRef}
              graphData={graphData}
              width={width}
              height={HEIGHT}
              backgroundColor="transparent"
              nodeLabel={(node) => `${node.standard_id}${node.title ? ` — ${node.title}` : ""}${node.status === "withdrawn" ? " (withdrawn)" : ""}`}
              nodeRelSize={4}
              nodeVal={(node) => (node.isFocus ? 6 : 2)}
              nodeCanvasObjectMode={() => "replace"}
              nodeCanvasObject={(node, context, globalScale) => {
                const n = node as GraphNode;
                if (n.x === undefined || n.y === undefined) return;
                const isDark = document.documentElement.dataset.theme === "dark";
                const isSelected = selected?.id === n.id;
                const radius = n.isFocus ? 9 : 5;

                context.beginPath();
                context.arc(n.x, n.y, radius, 0, 2 * Math.PI);
                context.fillStyle = n.isFocus
                  ? "#1678d2"
                  : n.status === "withdrawn"
                    ? "#d64545"
                    : n.retrieved
                      ? "#5aa6ea"
                      : isDark ? "#9aa8b6" : "#b9c6d3";
                context.fill();
                if (isSelected) {
                  context.lineWidth = 2 / globalScale;
                  context.strokeStyle = isDark ? "#ffffff" : "#1b2733";
                  context.stroke();
                }

                // Labels: always for the focus, and for neighbours once zoomed
                // in enough that they no longer collide.
                if (n.isFocus || globalScale > 1.1 || isSelected) {
                  const fontSize = (n.isFocus ? 13 : 11) / globalScale;
                  context.font = `${n.isFocus ? 700 : 500} ${fontSize}px sans-serif`;
                  context.textAlign = "center";
                  context.textBaseline = "top";
                  context.fillStyle = isDark ? "#e7edf3" : "#243747";
                  context.fillText(n.standard_id, n.x, n.y + radius + 2 / globalScale);
                }
              }}
              nodePointerAreaPaint={(node, color, context) => {
                const n = node as GraphNode;
                if (n.x === undefined || n.y === undefined) return;
                context.fillStyle = color;
                context.beginPath();
                context.arc(n.x, n.y, n.isFocus ? 11 : 7, 0, 2 * Math.PI);
                context.fill();
              }}
              linkLabel={(link) => RELATIONS[link.relationship as Relationship]?.label ?? link.relationship}
              linkColor={(link) => RELATIONS[link.relationship as Relationship]?.color ?? "#89919a"}
              linkLineDash={(link) => RELATIONS[link.relationship as Relationship]?.dash ?? null}
              linkWidth={(link) => (link.relationship === "NORMATIVELY_REFERENCES" ? 1.8 : 1.2)}
              linkDirectionalArrowLength={4}
              linkDirectionalArrowRelPos={1}
              onNodeClick={(node) => setSelected(node as GraphNode)}
              onBackgroundClick={() => setSelected(null)}
              cooldownTicks={120}
              onEngineStop={() => graphRef.current?.zoomToFit(400, 40)}
              enableNodeDrag
            />
          </div>

          <div className="flex flex-wrap items-center gap-x-5 gap-y-2 border-t border-border px-5 py-3 text-xs text-text-secondary">
            <span className="inline-flex items-center gap-2"><i className="size-2.5 rounded-full bg-[#1678d2]" />Selected recommendation</span>
            <span className="inline-flex items-center gap-2"><i className="size-2.5 rounded-full bg-[#5aa6ea]" />Also recommended</span>
            <span className="inline-flex items-center gap-2"><i className="size-2.5 rounded-full bg-[#b9c6d3]" />Related standard</span>
            <span className="inline-flex items-center gap-2"><i className="size-2.5 rounded-full bg-[#d64545]" />Withdrawn</span>
            <span className="text-text-muted">Scroll to zoom · labels appear when zoomed in · click a node for details</span>
          </div>

          {selected && graphData.nodes.some((n) => n.id === selected.id) && (
            <div className="border-t border-border bg-surface-muted px-5 py-3">
              <div className="flex flex-wrap items-baseline gap-x-2 gap-y-1">
                <strong className="text-sm text-text-primary">{selected.standard_id}</strong>
                <span className="text-xs text-text-muted">
                  {selected.retrieved ? "Recommended for this tender" : "Related standard"}
                </span>
              </div>
              {selected.title && <p className="mt-1 text-sm text-text-secondary">{selected.title}</p>}
              {selected.status && (
                <p className={`mt-1 text-xs capitalize ${selected.status === "withdrawn" ? "text-[#d64545]" : "text-text-muted"}`}>
                  Status: {selected.status}
                </p>
              )}
            </div>
          )}
        </>
      )}
    </section>
  );
}
