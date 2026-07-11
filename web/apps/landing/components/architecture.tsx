import { Reveal } from "@/components/reveal";
import { Section } from "@/components/section";

function Box({
  x,
  y,
  width,
  height,
  title,
  sub,
  accent = false,
}: {
  x: number;
  y: number;
  width: number;
  height: number;
  title: string;
  sub?: string;
  accent?: boolean;
}) {
  const cx = x + width / 2;
  return (
    <g>
      <rect
        x={x}
        y={y}
        width={width}
        height={height}
        rx={8}
        className={accent ? "fill-card stroke-primary/60" : "fill-card stroke-border"}
        strokeWidth={accent ? 1.25 : 1}
      />
      <text
        x={cx}
        y={sub ? y + height / 2 - 4 : y + height / 2 + 4}
        textAnchor="middle"
        className="fill-foreground font-mono text-[12px]"
      >
        {title}
      </text>
      {sub ? (
        <text
          x={cx}
          y={y + height / 2 + 14}
          textAnchor="middle"
          className="fill-muted-foreground font-mono text-[10px]"
        >
          {sub}
        </text>
      ) : null}
    </g>
  );
}

function Flow({ d, dashed = false }: { d: string; dashed?: boolean }) {
  return (
    <path
      d={d}
      fill="none"
      strokeWidth={1}
      strokeDasharray={dashed ? "4 4" : undefined}
      markerEnd="url(#arrow)"
      className="stroke-muted-foreground/50"
    />
  );
}

function FlowLabel({ x, y, children }: { x: number; y: number; children: string }) {
  return (
    <text x={x} y={y} className="fill-muted-foreground/80 font-mono text-[9.5px]">
      {children}
    </text>
  );
}

export function Architecture() {
  return (
    <Section
      id="architecture"
      number="02"
      label="architecture"
      title="Postgres is the system of record. Everything else is replaceable."
      intro="Redis can be flushed and rebuilt from Postgres. Workers, worktrees, and files are execution scratch. The record survives restarts, redeploys, and bad days."
    >
      <Reveal>
        <div className="overflow-x-auto rounded-lg border bg-card/40 p-4 sm:p-6">
          <svg
            viewBox="0 0 880 470"
            role="img"
            aria-label="spawnd architecture: CLI, Python API, HTTP API, and webhooks submit through the spawnd API into Postgres for durable state, Redis for coordination hints, and object storage for redacted artifacts. Workers claim agents in Postgres transactions and execute them in git worktrees with Claude Code or Codex CLI."
            className="h-auto w-full min-w-[740px] text-muted-foreground"
          >
            <defs>
              <marker
                id="arrow"
                viewBox="0 0 8 8"
                refX="7"
                refY="4"
                markerWidth="7"
                markerHeight="7"
                orient="auto-start-reverse"
              >
                <path d="M0 0.5 L7.5 4 L0 7.5 Z" className="fill-muted-foreground/60" />
              </marker>
            </defs>

            <Box x={144} y={16} width={130} height={36} title="cli" />
            <Box x={298} y={16} width={130} height={36} title="python api" />
            <Box x={452} y={16} width={130} height={36} title="http api" />
            <Box x={606} y={16} width={130} height={36} title="webhooks" />

            <Flow d="M209 52 V72 H340 V92" />
            <Flow d="M363 52 V72 H420 V92" />
            <Flow d="M517 52 V72 H500 V92" />
            <Flow d="M671 52 V72 H580 V92" />

            <Box
              x={280}
              y={96}
              width={320}
              height={52}
              title="spawnd api"
              sub="fastapi · bearer auth · plan validation"
            />

            <Flow d="M340 148 V172 H172 V196" />
            <Flow d="M460 148 V196" />
            <Flow d="M540 148 V172 H748 V196" />

            <Box
              x={56}
              y={200}
              width={232}
              height={60}
              title="postgres"
              sub="durable state · runs · leases"
              accent
            />
            <Box
              x={344}
              y={200}
              width={232}
              height={60}
              title="redis"
              sub="coordination only · rebuildable"
            />
            <Box
              x={632}
              y={200}
              width={232}
              height={60}
              title="object storage"
              sub="redacted artifacts"
            />

            <Flow d="M172 260 V286 H340 V310" />
            <Flow d="M380 310 V286 H212 V264" />
            <FlowLabel x={222} y={281}>
              claim tx · leases · facts
            </FlowLabel>
            <Flow d="M460 260 V310" dashed />
            <FlowLabel x={470} y={300}>
              wakeup hints
            </FlowLabel>
            <Flow d="M540 314 V286 H748 V264" />
            <FlowLabel x={612} y={281}>
              artifacts
            </FlowLabel>

            <Box
              x={280}
              y={314}
              width={320}
              height={52}
              title="workers"
              sub="claim in a postgres tx · execute · record facts"
            />

            <Flow d="M440 366 V402" />

            <Box
              x={240}
              y={406}
              width={400}
              height={48}
              title="git worktrees · claude code / codex cli"
              sub="execution scratch — never the record"
            />
          </svg>
        </div>
      </Reveal>
    </Section>
  );
}
