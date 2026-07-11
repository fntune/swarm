"use client";

import { CopyButton } from "@spawnd/ui/components/copy-button";
import { cn } from "@spawnd/ui/lib/utils";
import { useVirtualizer } from "@tanstack/react-virtual";
import { AnsiUp } from "ansi_up";
import { WrapTextIcon } from "lucide-react";
import * as React from "react";

const LINE_HEIGHT = 20;

export function AnsiLogPane({
  text,
  className,
  maxHeight = 420,
  redactionPolicy,
}: {
  text: string;
  className?: string;
  maxHeight?: number;
  redactionPolicy?: string | null;
}) {
  const [wrap, setWrap] = React.useState(false);
  const parentRef = React.useRef<HTMLDivElement | null>(null);
  const ansi = React.useMemo(() => {
    const converter = new AnsiUp();
    converter.escape_html = true;
    return converter;
  }, []);
  const lines = React.useMemo(() => text.replace(/\n$/, "").split("\n"), [text]);

  const virtualizer = useVirtualizer({
    count: lines.length,
    getScrollElement: () => parentRef.current,
    estimateSize: () => LINE_HEIGHT,
    overscan: 40,
  });

  return (
    <div className={cn("overflow-hidden rounded-md border border-zinc-800 bg-zinc-950", className)}>
      <div className="flex items-center justify-between border-zinc-800 border-b px-2 py-1">
        <span className="font-mono text-[11px] text-zinc-500">
          {lines.length.toLocaleString()} lines
          {redactionPolicy === "raw" ? " · raw capture" : ""}
        </span>
        <span className="flex items-center gap-0.5">
          <button
            type="button"
            title={wrap ? "Disable line wrap" : "Wrap lines"}
            onClick={() => setWrap((current) => !current)}
            className={cn(
              "rounded p-1 text-zinc-500 hover:bg-zinc-800 hover:text-zinc-200",
              wrap && "text-zinc-100",
            )}
          >
            <WrapTextIcon className="size-3.5" />
          </button>
          <CopyButton
            value={text}
            className="text-zinc-500 hover:bg-zinc-800 hover:text-zinc-200"
          />
        </span>
      </div>
      {wrap ? (
        <div
          className="overflow-auto p-3 font-mono text-[12px] text-zinc-200 leading-5"
          style={{ maxHeight }}
        >
          {lines.map((line, index) => (
            <div
              // log lines are positional; index keys are correct here
              key={index}
              className="whitespace-pre-wrap break-all"
              dangerouslySetInnerHTML={{ __html: ansi.ansi_to_html(line) || "&nbsp;" }}
            />
          ))}
        </div>
      ) : (
        <div ref={parentRef} className="overflow-auto p-3" style={{ maxHeight }}>
          <div
            className="relative w-full font-mono text-[12px] text-zinc-200"
            style={{ height: virtualizer.getTotalSize() }}
          >
            {virtualizer.getVirtualItems().map((row) => (
              <div
                key={row.key}
                className="absolute top-0 left-0 w-full whitespace-pre leading-5"
                style={{ transform: `translateY(${row.start}px)` }}
                dangerouslySetInnerHTML={{
                  __html: ansi.ansi_to_html(lines[row.index] ?? "") || "&nbsp;",
                }}
              />
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
