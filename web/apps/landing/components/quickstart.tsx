import { CopyButton } from "@spawnd/ui/components/copy-button";

import { Reveal } from "@/components/reveal";
import { Section } from "@/components/section";

function CommandBlock({ lines }: { lines: string[] }) {
  return (
    <div className="relative overflow-x-auto rounded-lg border border-zinc-700/60 bg-zinc-950 py-3 pr-12 pl-4">
      <CopyButton
        value={lines.join("\n")}
        className="absolute top-1.5 right-1.5 text-zinc-500 hover:bg-zinc-800 hover:text-zinc-200"
      />
      <pre className="font-mono text-[13px] text-zinc-200 leading-relaxed">{lines.join("\n")}</pre>
    </div>
  );
}

const STEPS = [
  {
    title: "Bring up the stack",
    body: "Postgres, Redis, MinIO, the API, a worker, and an OTel collector — one compose file.",
    lines: ["git clone https://github.com/fntune/spawnd.git", "cd spawnd", "docker compose up -d"],
  },
  {
    title: "Point the CLI at it",
    body: "The CLI reads and writes the same deployed services as the HTTP API and the dashboard.",
    lines: [
      "pip install -e .",
      "export SPAWND_DATABASE_URL='postgresql+psycopg://spawnd:spawnd@localhost:54329/spawnd'",
      "export SPAWND_REDIS_URL='redis://localhost:63799/0'",
    ],
  },
  {
    title: "Submit a plan",
    body: "Watch the DAG execute wave by wave; status shows agents, checks, and spend.",
    lines: ["spawnd run -f plan.yaml", "spawnd status"],
  },
];

export function Quickstart() {
  return (
    <Section
      id="quickstart"
      number="04"
      label="quickstart"
      title="Up in three commands."
      intro="The compose stack is the deployment — the same services run in dev and in production."
    >
      <div className="flex flex-col gap-8">
        {STEPS.map((step, index) => (
          <Reveal key={step.title}>
            <div className="grid items-start gap-4 md:grid-cols-[220px_minmax(0,1fr)] md:gap-8">
              <div className="flex flex-col gap-1">
                <p className="font-mono text-muted-foreground/70 text-xs">
                  step {String(index + 1).padStart(2, "0")}
                </p>
                <h3 className="font-medium text-sm">{step.title}</h3>
                <p className="text-[13px] text-muted-foreground leading-relaxed">{step.body}</p>
              </div>
              <CommandBlock lines={step.lines} />
            </div>
          </Reveal>
        ))}
      </div>
    </Section>
  );
}
