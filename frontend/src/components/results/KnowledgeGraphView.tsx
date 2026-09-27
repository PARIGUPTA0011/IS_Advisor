import { useEffect, useMemo, useRef, useState } from "react";
import ForceGraph2D, { type ForceGraphMethods } from "react-force-graph-2d";
import { Network } from "lucide-react";
import type { KnowledgeGraphEdge, KnowledgeGraphNode } from "../../types/api";

interface Props {
  nodes: KnowledgeGraphNode[];
  edges: KnowledgeGraphEdge[];
}

interface GraphNode extends KnowledgeGraphNode {
  x?: number;
  y?: number;
  fx?: number;
  fy?: number;
  isPrimary?: boolean;
}

interface GraphLink extends Omit<KnowledgeGraphEdge, "source" | "target"> {
  source: string | GraphNode;
  target: string | GraphNode;
}

function drawEllipsizedText(
  context: CanvasRenderingContext2D,
  text: string,
  x: number,
  y: number,
  maxWidth: number,
) {
  const characters = Array.from(text);
  let label = text;
  while (label && context.measureText(label).width > maxWidth) {
    characters.pop();
    label = `${characters.join("")}...`;
  }
  context.fillText(label, x, y);
}

const RELATION_COLORS: Record<string, string> = {
  REFERENCES: "#287c70",
  REFERENCED_BY: "#287c70",
  REPLACED_BY: "#cf7938",
  REPLACES: "#cf7938",
};

export function KnowledgeGraphView({ nodes, edges }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const graphRef = useRef<ForceGraphMethods<GraphNode, GraphLink>>();
  const [width, setWidth] = useState(720);
  const [selectedNode, setSelectedNode] = useState<KnowledgeGraphNode | null>(null);

  const graphData = useMemo(() => {
    const primaryId = nodes.find((node) => node.retrieved)?.id ?? nodes[0]?.id;
    return {
      nodes: nodes.map((node) => ({
        ...node,
        isPrimary: node.id === primaryId,
        ...(node.id === primaryId ? { fx: 0, fy: 0 } : {}),
      })),
      links: edges.map((edge) => ({ ...edge })),
    };
  }, [edges, nodes]);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    const observer = new ResizeObserver(([entry]) => {
      setWidth(Math.floor(entry.contentRect.width));
    });
    observer.observe(container);
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    const linkForce = graphRef.current?.d3Force("link");
    linkForce?.distance(150);
    graphRef.current?.d3Force("charge")?.strength(-420);
  }, [graphData]);

  return (
    <section className="glass-panel overflow-hidden rounded-2xl">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border px-5 py-4">
        <div className="flex items-center gap-3">
          <span className="flex size-9 items-center justify-center rounded-lg bg-accent-gold-soft text-accent-gold">
            <Network size={18} />
          </span>
          <div>
            <h2 className="text-sm font-semibold text-text-primary">Knowledge graph</h2>
            <p className="text-xs text-text-muted">Standards and relationships for this tender</p>
          </div>
        </div>
        <div className="flex gap-3 text-xs text-text-secondary">
          <span>{nodes.length} standards</span>
          <span>{edges.length} relationships</span>
        </div>
      </div>

      {nodes.length === 0 ? (
        <div className="flex min-h-56 flex-col items-center justify-center px-6 text-center">
          <Network size={24} className="text-text-muted" />
          <p className="mt-3 text-sm font-medium text-text-primary">No graph relationships found</p>
          <p className="mt-1 max-w-sm text-xs text-text-muted">
            This analysis did not retrieve standards with connected Neo4j relationships.
          </p>
        </div>
      ) : (
        <>
          <div ref={containerRef} className="h-[400px] w-full bg-[var(--bg-elevated)]">
            <ForceGraph2D
              ref={graphRef}
              graphData={graphData}
              width={width}
              height={400}
              backgroundColor="transparent"
              nodeLabel={(node) => `${node.standard_id}${node.title ? `: ${node.title}` : ""}`}
              nodeCanvasObjectMode={() => "replace"}
              nodeCanvasObject={(node, context, globalScale) => {
                const graphNode = node as GraphNode;
                if (graphNode.x === undefined || graphNode.y === undefined) return;

                const radius = (graphNode.isPrimary ? 74 : graphNode.retrieved ? 56 : 48) / globalScale;
                const isSelected = selectedNode?.id === graphNode.id;
                const isDark = document.documentElement.dataset.theme === "dark";

                context.beginPath();
                context.arc(graphNode.x, graphNode.y, radius + (isSelected ? 4 : 0) / globalScale, 0, 2 * Math.PI);
                context.fillStyle = graphNode.isPrimary
                  ? "#1678d2"
                  : graphNode.retrieved
                    ? (isDark ? "#173d61" : "#e6f3ff")
                    : (isDark ? "#292d35" : "#ffffff");
                context.fill();
                context.lineWidth = (isSelected ? 3 : graphNode.isPrimary ? 2.5 : 1.5) / globalScale;
                context.strokeStyle = isSelected || graphNode.isPrimary
                  ? (isDark ? "#ffffff" : "#1764a5")
                  : (isDark ? "#71859a" : "#8ab8df");
                context.stroke();

                context.textAlign = "center";
                context.textBaseline = "middle";
                const numberFontSize = (graphNode.isPrimary ? 13 : 10) / globalScale;
                const titleFontSize = (graphNode.isPrimary ? 11 : 9) / globalScale;
                const textColor = graphNode.isPrimary ? "#ffffff" : isDark ? "#e7edf3" : "#243747";
                context.fillStyle = textColor;
                let fittedNumberFontSize = numberFontSize;
                context.font = `600 ${fittedNumberFontSize}px sans-serif`;
                while (
                  context.measureText(graphNode.standard_id).width > radius * 1.7 &&
                  fittedNumberFontSize > 7 / globalScale
                ) {
                  fittedNumberFontSize -= 0.5 / globalScale;
                  context.font = `600 ${fittedNumberFontSize}px sans-serif`;
                }
                context.fillText(graphNode.standard_id, graphNode.x, graphNode.y - 7 / globalScale);

                if (graphNode.title) {
                  context.fillStyle = graphNode.isPrimary ? "rgba(255,255,255,0.88)" : isDark ? "#b8c4d0" : "#617587";
                  context.font = `400 ${titleFontSize}px sans-serif`;
                  drawEllipsizedText(context, graphNode.title, graphNode.x, graphNode.y + 12 / globalScale, radius * 1.65);
                }
              }}
              nodeVal={(node) => node.isPrimary ? 40 : 18}
              linkLabel={(link) => link.relationship}
              linkColor={(link) => RELATION_COLORS[link.relationship] ?? "#89919a"}
              linkLineDash={(link) => ["REFERENCES", "REFERENCED_BY"].includes(link.relationship) ? [5, 4] : null}
              linkWidth={(link) => link.relationship === "REPLACED_BY" || link.relationship === "REPLACES" ? 2 : 1.4}
              linkDirectionalArrowLength={5}
              linkDirectionalArrowRelPos={1}
              onNodeClick={(node) => setSelectedNode(node as GraphNode)}
              cooldownTicks={100}
              enableNodeDrag
            />
          </div>

          <div className="flex flex-wrap items-center gap-x-5 gap-y-2 border-t border-border px-5 py-3 text-xs text-text-secondary">
            <span className="inline-flex items-center gap-2"><i className="size-2.5 rounded-full bg-[#1678d2]" />Tender standard</span>
            <span className="inline-flex items-center gap-2"><i className="size-2.5 rounded-full border border-[#8ab8df] bg-white" />Connected standard</span>
            <span className="inline-flex items-center gap-2"><i className="h-0.5 w-5 border-t-2 border-dashed border-[#287c70]" />References</span>
            <span className="inline-flex items-center gap-2"><i className="h-0.5 w-5 border-t-2 border-[#cf7938]" />Replacements</span>
          </div>

          {selectedNode && (
            <div className="border-t border-border bg-surface-muted px-5 py-3">
              <div className="flex flex-wrap items-baseline gap-x-2 gap-y-1">
                <strong className="text-sm text-text-primary">{selectedNode.standard_id}</strong>
                <span className="text-xs text-text-muted">{selectedNode.retrieved ? "Retrieved for this tender" : "Neo4j neighbor"}</span>
              </div>
              {selectedNode.title && <p className="mt-1 text-sm text-text-secondary">{selectedNode.title}</p>}
              {selectedNode.status && <p className="mt-1 text-xs capitalize text-text-muted">Status: {selectedNode.status}</p>}
            </div>
          )}
        </>
      )}
    </section>
  );
}