"use client";

import type { Agent } from "@spawnd/api-client";
import { Background, Controls, type NodeTypes, ReactFlow, ReactFlowProvider } from "@xyflow/react";
import { useTheme } from "next-themes";
import * as React from "react";

import { layoutDag } from "@/lib/dag-layout";
import { AgentNode } from "./agent-node";

import "@xyflow/react/dist/style.css";

const nodeTypes: NodeTypes = { agent: AgentNode as NodeTypes[string] };

export function DagCanvas({
  agents,
  selectedAgent,
  onSelectAgent,
}: {
  agents: Agent[];
  selectedAgent: string | null;
  onSelectAgent: (agent: string | null) => void;
}) {
  const { resolvedTheme } = useTheme();
  // Mount the canvas only once the theme is resolved so xyflow initializes
  // with the right color mode (its colorMode prop is read at mount).
  const [mounted, setMounted] = React.useState(false);
  React.useEffect(() => {
    setMounted(true);
  }, []);

  const { nodes, edges } = React.useMemo(
    () => layoutDag(agents, selectedAgent),
    [agents, selectedAgent],
  );

  if (!mounted) {
    return <div className="h-full w-full bg-background" />;
  }

  return (
    <ReactFlowProvider>
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        colorMode={resolvedTheme === "dark" ? "dark" : "light"}
        fitView
        fitViewOptions={{ padding: 0.2, maxZoom: 1 }}
        minZoom={0.2}
        maxZoom={1.5}
        nodesDraggable={false}
        nodesConnectable={false}
        edgesFocusable={false}
        proOptions={{ hideAttribution: true }}
        onNodeClick={(_, node) => onSelectAgent(node.id === selectedAgent ? null : node.id)}
        onPaneClick={() => onSelectAgent(null)}
        className="bg-background"
      >
        <Background gap={24} size={1} />
        <Controls showInteractive={false} />
      </ReactFlow>
    </ReactFlowProvider>
  );
}
