import {
  Activity,
  BadgeCheck,
  CalendarClock,
  CircleDollarSign,
  Database,
  EyeOff,
  GitFork,
  SquareTerminal,
} from "lucide-react";

import { Reveal } from "@/components/reveal";
import { Section } from "@/components/section";

const FEATURES = [
  {
    icon: Database,
    title: "Postgres is the record",
    body: "Runs, attempts, leases, events, checks, usage, traces — durable rows. Redis only coordinates and can be rebuilt from Postgres.",
  },
  {
    icon: GitFork,
    title: "Agent DAGs",
    body: "Declare depends_on in YAML. spawnd schedules waves, retries failed attempts, and only enqueues dependents when parents pass.",
  },
  {
    icon: BadgeCheck,
    title: "Verified completion",
    body: "Every agent runs your check command in its worktree. Exit codes decide success — not the model's opinion of its own work.",
  },
  {
    icon: CircleDollarSign,
    title: "Cost budgets",
    body: "Per-agent caps and a plan-level budget that pauses, cancels, or warns on breach. Token and cost rows recorded per attempt.",
  },
  {
    icon: EyeOff,
    title: "Redacted by default",
    body: "Setup logs, runtime output, patches, and provider payloads are scrubbed before upload. .env contents are never persisted.",
  },
  {
    icon: Activity,
    title: "Observable end to end",
    body: "OpenTelemetry export plus a redacted trace mirror in Postgres. Live event streams over SSE, from submission to cleanup.",
  },
  {
    icon: CalendarClock,
    title: "Templates & schedules",
    body: "Parameterized run templates, interval schedules, and GitHub webhook submission — all through one deployed submission path.",
  },
  {
    icon: SquareTerminal,
    title: "Multi-runtime",
    body: "Claude Code and Codex CLI executors behind one observer contract. Mix runtimes and models per agent in the same plan.",
  },
];

export function Features() {
  return (
    <Section
      id="capabilities"
      number="01"
      label="capabilities"
      title="Built for runs you can defend."
      intro="Every capability maps to rows you can query after the fact — not a vibe in terminal scrollback."
    >
      <Reveal>
        <div className="grid grid-cols-1 gap-px overflow-hidden rounded-lg border bg-border sm:grid-cols-2 lg:grid-cols-4">
          {FEATURES.map((feature, index) => (
            <div key={feature.title} className="flex flex-col gap-3 bg-background p-5">
              <div className="flex items-center justify-between">
                <feature.icon aria-hidden="true" className="size-4 text-primary" />
                <span className="font-mono text-[11px] text-muted-foreground/70">
                  {String(index + 1).padStart(2, "0")}
                </span>
              </div>
              <h3 className="font-medium text-sm">{feature.title}</h3>
              <p className="text-[13px] text-muted-foreground leading-relaxed">{feature.body}</p>
            </div>
          ))}
        </div>
      </Reveal>
    </Section>
  );
}
