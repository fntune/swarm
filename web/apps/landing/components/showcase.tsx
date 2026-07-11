import { TerminalFrame } from "@spawnd/ui/components/terminal-frame";

import { Reveal } from "@/components/reveal";
import { Section } from "@/components/section";

/** YAML token tints, scoped to the always-dark terminal frame. */
function K({ children }: { children: string }) {
  return <span className="text-indigo-300">{children}</span>;
}
function V({ children }: { children: string }) {
  return <span className="text-zinc-300">{children}</span>;
}
function C({ children }: { children: string }) {
  return <span className="text-emerald-300/90">{children}</span>;
}
function B({ children }: { children: string }) {
  return <span className="text-zinc-100">{children}</span>;
}
function N({ children }: { children: string }) {
  return <span className="text-amber-300">{children}</span>;
}

function PlanYaml() {
  return (
    <div className="whitespace-pre text-zinc-600">
      <div>
        <K>name</K>: <V>nightly-refactor</V>
      </div>
      <div>
        <K>cost_budget</K>:
      </div>
      <div>
        {"  "}
        <K>total_usd</K>: <N>10</N>
      </div>
      <div>
        {"  "}
        <K>on_exceed</K>: <V>pause</V>
      </div>
      <div>{" "}</div>
      <div>
        <K>agents</K>:
      </div>
      <div>
        {"  - "}
        <K>name</K>: <B>planner</B>
      </div>
      <div>
        {"    "}
        <K>prompt</K>: <V>Map the migration; write tasks.md</V>
      </div>
      <div>
        {"    "}
        <K>check</K>: <C>test -f tasks.md</C>
      </div>
      <div>{" "}</div>
      <div>
        {"  - "}
        <K>name</K>: <B>impl-api</B>
      </div>
      <div>
        {"    "}
        <K>depends_on</K>: [<B>planner</B>]
      </div>
      <div>
        {"    "}
        <K>prompt</K>: <V>Land the API tasks from tasks.md</V>
      </div>
      <div>
        {"    "}
        <K>check</K>: <C>pytest tests/api</C>
      </div>
      <div>{" "}</div>
      <div>
        {"  - "}
        <K>name</K>: <B>impl-web</B>
      </div>
      <div>
        {"    "}
        <K>depends_on</K>: [<B>planner</B>]
      </div>
      <div>
        {"    "}
        <K>runtime</K>: <V>codex</V>
      </div>
      <div>
        {"    "}
        <K>prompt</K>: <V>Land the web tasks from tasks.md</V>
      </div>
      <div>
        {"    "}
        <K>check</K>: <C>pnpm test</C>
      </div>
      <div>{" "}</div>
      <div>
        {"  - "}
        <K>name</K>: <B>reviewer</B>
      </div>
      <div>
        {"    "}
        <K>depends_on</K>: [<B>impl-api</B>, <B>impl-web</B>]
      </div>
      <div>
        {"    "}
        <K>prompt</K>: <V>Review both diffs; fix the nits</V>
      </div>
      <div>
        {"    "}
        <K>check</K>: <C>./scripts/ci.sh</C>
      </div>
    </div>
  );
}

type NodeStatus = "completed" | "running" | "pending";

const DOT_CLASS: Record<NodeStatus, string> = {
  completed: "fill-status-completed",
  running: "fill-status-running",
  pending: "fill-muted-foreground/50",
};

const NODES: {
  name: string;
  x: number;
  y: number;
  status: NodeStatus;
  meta: string;
  cost: string;
}[] = [
  { name: "planner", x: 20, y: 118, status: "completed", meta: "claude", cost: "$0.41" },
  { name: "impl-api", x: 262, y: 30, status: "completed", meta: "claude", cost: "$0.78" },
  { name: "impl-web", x: 262, y: 206, status: "running", meta: "codex", cost: "$0.36" },
  { name: "reviewer", x: 504, y: 118, status: "pending", meta: "claude", cost: "—" },
];

const EDGES: { id: string; d: string; animated: boolean }[] = [
  { id: "planner-impl-api", d: "M196 150 C230 150 228 62 262 62", animated: false },
  { id: "planner-impl-web", d: "M196 150 C230 150 228 238 262 238", animated: true },
  { id: "impl-api-reviewer", d: "M438 62 C472 62 470 150 504 150", animated: false },
  { id: "impl-web-reviewer", d: "M438 238 C472 238 470 150 504 150", animated: false },
];

function PlanDag() {
  return (
    <svg
      viewBox="0 0 700 300"
      role="img"
      aria-label="The plan rendered as a DAG: planner completed, impl-api completed, impl-web running, reviewer pending until both implementations pass."
      className="h-auto w-full min-w-[540px]"
    >
      {EDGES.map((edge) =>
        edge.animated ? (
          <path
            key={edge.id}
            d={edge.d}
            fill="none"
            strokeWidth={1.5}
            strokeDasharray="6 4"
            className="motion-safe:animate-dash-flow stroke-status-running/70"
          />
        ) : (
          <path
            key={edge.id}
            d={edge.d}
            fill="none"
            strokeWidth={1.5}
            className="stroke-muted-foreground/40"
          />
        ),
      )}
      {NODES.map((node) => (
        <g key={node.name}>
          <rect
            x={node.x}
            y={node.y}
            width={176}
            height={64}
            rx={8}
            strokeWidth={node.status === "running" ? 1.25 : 1}
            className={
              node.status === "running"
                ? "fill-card stroke-status-running/60"
                : "fill-card stroke-border"
            }
          />
          <text
            x={node.x + 14}
            y={node.y + 26}
            className="fill-foreground font-medium font-mono text-[12.5px]"
          >
            {node.name}
          </text>
          <text
            x={node.x + 162}
            y={node.y + 26}
            textAnchor="end"
            className="fill-muted-foreground font-mono text-[10px]"
          >
            {node.cost}
          </text>
          <circle cx={node.x + 18} cy={node.y + 44} r={3} className={DOT_CLASS[node.status]} />
          <text
            x={node.x + 27}
            y={node.y + 47.5}
            className="fill-muted-foreground font-mono text-[10px]"
          >
            {node.status}
          </text>
          <text
            x={node.x + 162}
            y={node.y + 47.5}
            textAnchor="end"
            className="fill-muted-foreground/80 font-mono text-[10px]"
          >
            {node.meta}
          </text>
        </g>
      ))}
    </svg>
  );
}

const READS = [
  {
    label: "waves",
    body: "planner runs alone; impl-api and impl-web are enqueued in parallel the moment its check passes.",
  },
  {
    label: "gates",
    body: "reviewer stays pending until both implementation checks exit 0 — failed checks retry the agent, not the run.",
  },
  {
    label: "budget",
    body: "cost_budget pauses the whole run at $10. Spend is recorded per attempt, so the cap is enforced mid-flight.",
  },
];

export function Showcase() {
  return (
    <Section
      id="plans"
      number="03"
      label="plans"
      title="A YAML plan in. A durable DAG out."
      intro="depends_on becomes scheduling waves, check commands gate dependents, and the budget is enforced while agents run — the plan is the contract."
    >
      <div className="grid items-start gap-6 lg:grid-cols-2">
        <Reveal>
          <TerminalFrame title="plan.yaml" bodyClassName="max-h-[560px]">
            <PlanYaml />
          </TerminalFrame>
        </Reveal>
        <Reveal delay={0.1} className="flex flex-col gap-6">
          <div className="overflow-x-auto rounded-lg border bg-card/40 p-4 sm:p-5">
            <PlanDag />
          </div>
          <ol className="overflow-hidden rounded-lg border">
            {READS.map((read, index) => (
              <li key={read.label} className="flex gap-4 border-t px-4 py-3.5 first:border-t-0">
                <span className="font-mono text-muted-foreground/70 text-xs">
                  {String(index + 1).padStart(2, "0")}
                </span>
                <div className="flex flex-col gap-0.5">
                  <span className="font-mono text-foreground text-xs">{read.label}</span>
                  <span className="text-[13px] text-muted-foreground leading-relaxed">
                    {read.body}
                  </span>
                </div>
              </li>
            ))}
          </ol>
        </Reveal>
      </div>
    </Section>
  );
}
