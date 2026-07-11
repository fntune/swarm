"use client";

import * as React from "react";

type Tone = "bright" | "ok" | "accent";
type Segment = { text: string; tone?: Tone };
type Line = { id: string; segments: Segment[] };
type Beat = { id: string; command: string; output: Line[] };

const TONE_CLASS: Record<Tone, string> = {
  bright: "text-zinc-100",
  ok: "text-emerald-400",
  accent: "text-indigo-400",
};

/** Real spawnd CLI output shapes; timestamps shortened for the frame. */
const BEATS: Beat[] = [
  {
    id: "run",
    command: "spawnd run -f plan.yaml",
    output: [
      {
        id: "submitted",
        segments: [{ text: "Submitted run: " }, { text: "nightly-refactor", tone: "bright" }],
      },
    ],
  },
  {
    id: "events",
    command: "spawnd events nightly-refactor --limit 4",
    output: [
      {
        id: "ev-1",
        segments: [{ text: "12:05:58 impl-api " }, { text: "git_committed", tone: "bright" }],
      },
      { id: "ev-2", segments: [{ text: "12:06:01 impl-api worktree_cleaned" }] },
      {
        id: "ev-3",
        segments: [{ text: "12:06:24 impl-web " }, { text: "git_committed", tone: "bright" }],
      },
      {
        id: "ev-4",
        segments: [{ text: "12:06:27 reviewer " }, { text: "agent_ready", tone: "accent" }],
      },
    ],
  },
  {
    id: "status",
    command: "spawnd status nightly-refactor",
    output: [
      { id: "st-run", segments: [{ text: "Run: nightly-refactor" }] },
      { id: "st-plan", segments: [{ text: "Plan: nightly-refactor" }] },
      {
        id: "st-status",
        segments: [{ text: "Status: " }, { text: "completed", tone: "ok" }],
      },
      { id: "st-cost", segments: [{ text: "Cost: " }, { text: "$2.4610", tone: "bright" }] },
      { id: "st-blank", segments: [{ text: "" }] },
      { id: "st-agents", segments: [{ text: "Agents:" }] },
      {
        id: "st-planner",
        segments: [{ text: "  planner: " }, { text: "completed", tone: "ok" }],
      },
      {
        id: "st-impl-api",
        segments: [{ text: "  impl-api: " }, { text: "completed", tone: "ok" }],
      },
      {
        id: "st-impl-web",
        segments: [{ text: "  impl-web: " }, { text: "completed", tone: "ok" }],
      },
      {
        id: "st-reviewer",
        segments: [{ text: "  reviewer: " }, { text: "completed", tone: "ok" }],
      },
    ],
  },
];

type Progress = { beat: number; chars: number; lines: number };

const FINISHED: Progress = { beat: BEATS.length, chars: 0, lines: 0 };
const TYPE_MS = 26;
const FIRST_OUTPUT_MS = 320;
const OUTPUT_LINE_MS = 90;
const BETWEEN_BEATS_MS = 650;

function Cursor() {
  return (
    <span
      aria-hidden="true"
      className="ml-px inline-block h-[1.05em] w-[0.55em] translate-y-[0.18em] bg-zinc-300 motion-safe:animate-terminal-caret"
    />
  );
}

function Prompt() {
  return <span className="select-none text-indigo-400">$ </span>;
}

function OutputLine({ line }: { line: Line }) {
  return (
    <div className="min-h-[1.625em] whitespace-pre text-zinc-400">
      {line.segments.map((segment) => (
        <span
          key={`${line.id}:${segment.text}`}
          className={segment.tone ? TONE_CLASS[segment.tone] : undefined}
        >
          {segment.text}
        </span>
      ))}
    </div>
  );
}

export function Transcript() {
  const [progress, setProgress] = React.useState<Progress>({ beat: 0, chars: 0, lines: 0 });

  React.useEffect(() => {
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      setProgress(FINISHED);
      return;
    }
    let cancelled = false;
    let timer = 0;
    const step = (current: Progress) => {
      if (cancelled) {
        return;
      }
      setProgress(current);
      const beat = BEATS[current.beat];
      if (!beat) {
        return;
      }
      if (current.chars < beat.command.length) {
        timer = window.setTimeout(() => step({ ...current, chars: current.chars + 1 }), TYPE_MS);
      } else if (current.lines < beat.output.length) {
        timer = window.setTimeout(
          () => step({ ...current, lines: current.lines + 1 }),
          current.lines === 0 ? FIRST_OUTPUT_MS : OUTPUT_LINE_MS,
        );
      } else {
        timer = window.setTimeout(
          () => step({ beat: current.beat + 1, chars: 0, lines: 0 }),
          BETWEEN_BEATS_MS,
        );
      }
    };
    timer = window.setTimeout(() => step({ beat: 0, chars: 0, lines: 0 }), 400);
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, []);

  const done = progress.beat >= BEATS.length;

  return (
    <>
      <p className="sr-only">
        Terminal transcript: spawnd run submits a plan, spawnd events shows agents committing and
        dependents becoming ready, and spawnd status reports the run completed with every agent
        passing for $2.46.
      </p>
      <div aria-hidden="true">
        {BEATS.map((beat, index) => {
          if (index > progress.beat) {
            return null;
          }
          const isCurrent = index === progress.beat;
          const typed = isCurrent ? beat.command.slice(0, progress.chars) : beat.command;
          const typing = isCurrent && progress.chars < beat.command.length;
          const visibleLines = isCurrent ? beat.output.slice(0, progress.lines) : beat.output;
          return (
            <div key={beat.id}>
              <div className="whitespace-pre text-zinc-100">
                <Prompt />
                {typed}
                {typing ? <Cursor /> : null}
              </div>
              {visibleLines.map((line) => (
                <OutputLine key={line.id} line={line} />
              ))}
            </div>
          );
        })}
        {done ? (
          <div>
            <Prompt />
            <Cursor />
          </div>
        ) : null}
      </div>
    </>
  );
}
