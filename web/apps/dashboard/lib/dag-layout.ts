import dagre from "@dagrejs/dagre";
import type { Agent } from "@spawnd/api-client";

export const DAG_NODE_WIDTH = 224;
export const DAG_NODE_HEIGHT = 78;

export interface DagNode {
  id: string;
  type: "agent";
  position: { x: number; y: number };
  data: { agent: Agent };
  selected?: boolean;
}

export interface DagEdge {
  id: string;
  source: string;
  target: string;
  /** Dash-flow only while the downstream agent is actually running. */
  animated: boolean;
}

export function layoutDag(agents: Agent[], selectedAgent?: string | null) {
  const graph = new dagre.graphlib.Graph();
  graph.setGraph({ rankdir: "LR", nodesep: 28, ranksep: 64, marginx: 16, marginy: 16 });
  graph.setDefaultEdgeLabel(() => ({}));

  const byName = new Map(agents.map((agent) => [agent.name, agent]));
  for (const agent of agents) {
    graph.setNode(agent.name, { width: DAG_NODE_WIDTH, height: DAG_NODE_HEIGHT });
  }

  const edges: DagEdge[] = [];
  for (const agent of agents) {
    for (const dependency of agent.depends_on ?? []) {
      if (!byName.has(dependency)) continue;
      graph.setEdge(dependency, agent.name);
      edges.push({
        id: `${dependency}->${agent.name}`,
        source: dependency,
        target: agent.name,
        animated: agent.status === "running",
      });
    }
  }

  dagre.layout(graph);

  const nodes: DagNode[] = agents.map((agent) => {
    const placed = graph.node(agent.name);
    return {
      id: agent.name,
      type: "agent",
      position: {
        x: placed.x - DAG_NODE_WIDTH / 2,
        y: placed.y - DAG_NODE_HEIGHT / 2,
      },
      data: { agent },
      selected: agent.name === selectedAgent,
    };
  });

  return { nodes, edges };
}
