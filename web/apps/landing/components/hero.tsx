import { TerminalFrame } from "@spawnd/ui/components/terminal-frame";
import { Button } from "@spawnd/ui/components/ui/button";

import { GITHUB_URL, GitHubMark } from "@/components/github";
import { Reveal } from "@/components/reveal";
import { Transcript } from "@/components/transcript";

const TRAITS = ["postgres-durable", "budget-capped", "check-verified", "redacted-by-default"];

export function Hero() {
  return (
    <section className="relative overflow-hidden px-6 py-16 sm:px-10 sm:py-24">
      <div
        aria-hidden="true"
        className="pointer-events-none absolute inset-0 bg-[radial-gradient(52rem_26rem_at_80%_-10%,color-mix(in_oklab,var(--color-primary)_14%,transparent),transparent_70%)]"
      />
      <div className="relative grid items-center gap-12 lg:grid-cols-[1fr_minmax(0,30rem)]">
        <Reveal className="flex flex-col items-start gap-6">
          <p className="font-mono text-muted-foreground text-xs uppercase tracking-[0.2em]">
            deployed-first agent orchestration
          </p>
          <h1 className="max-w-xl text-balance font-semibold text-4xl tracking-tight sm:text-5xl">
            Run fleets of coding agents like deployed software.
          </h1>
          <p className="max-w-xl text-balance text-[15px] text-muted-foreground leading-relaxed sm:text-base">
            spawnd executes DAGs of Claude Code and Codex agents against real repositories — every
            attempt, check, artifact, and dollar recorded in Postgres. Redis only coordinates.
            Workers are disposable.
          </p>
          <div className="flex flex-wrap items-center gap-3">
            <Button asChild>
              <a href={GITHUB_URL} target="_blank" rel="noreferrer">
                <GitHubMark className="size-4" />
                View on GitHub
              </a>
            </Button>
            <Button asChild variant="outline">
              <a href="#quickstart">Quickstart</a>
            </Button>
          </div>
          <p className="flex flex-wrap gap-x-3 gap-y-1 font-mono text-muted-foreground text-xs">
            {TRAITS.map((trait, index) => (
              <span key={trait} className="flex items-center gap-3">
                {index > 0 ? (
                  <span aria-hidden="true" className="text-border">
                    ·
                  </span>
                ) : null}
                {trait}
              </span>
            ))}
          </p>
        </Reveal>
        <Reveal delay={0.1}>
          <TerminalFrame title="operator@prod — spawnd" bodyClassName="h-[430px]">
            <Transcript />
          </TerminalFrame>
        </Reveal>
      </div>
    </section>
  );
}
