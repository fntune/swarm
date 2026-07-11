"use client";

import { cn } from "@spawnd/ui/lib/utils";
import * as React from "react";
import { Diff, Hunk, parseDiff } from "react-diff-view";

import "react-diff-view/style/index.css";

export function DiffViewer({ patch, className }: { patch: string; className?: string }) {
  const [split, setSplit] = React.useState(false);
  const files = React.useMemo(() => {
    try {
      return parseDiff(patch);
    } catch {
      return null;
    }
  }, [patch]);

  if (!files || files.length === 0) {
    return (
      <pre className="overflow-auto rounded-md border bg-muted/40 p-3 font-mono text-xs">
        {patch}
      </pre>
    );
  }

  return (
    <div className={cn("flex flex-col gap-3", className)}>
      <div className="flex items-center justify-end">
        <button
          type="button"
          onClick={() => setSplit((current) => !current)}
          className="rounded-md border px-2 py-0.5 font-mono text-muted-foreground text-xs hover:text-foreground"
        >
          {split ? "unified" : "split"}
        </button>
      </div>
      {files.map((file) => (
        <div key={`${file.oldPath}->${file.newPath}`} className="overflow-hidden rounded-md border">
          <div className="flex items-center gap-2 border-b bg-muted/40 px-3 py-1.5 font-mono text-xs">
            <span className="truncate">
              {file.type === "rename"
                ? `${file.oldPath} → ${file.newPath}`
                : file.newPath || file.oldPath}
            </span>
            <span className="ml-auto shrink-0 text-status-completed">
              +
              {file.hunks.reduce(
                (sum, hunk) => sum + hunk.changes.filter((c) => c.type === "insert").length,
                0,
              )}
            </span>
            <span className="shrink-0 text-status-failed">
              −
              {file.hunks.reduce(
                (sum, hunk) => sum + hunk.changes.filter((c) => c.type === "delete").length,
                0,
              )}
            </span>
          </div>
          <div className="overflow-x-auto font-mono text-xs">
            <Diff viewType={split ? "split" : "unified"} diffType={file.type} hunks={file.hunks}>
              {(hunks) => hunks.map((hunk) => <Hunk key={hunk.content} hunk={hunk} />)}
            </Diff>
          </div>
        </div>
      ))}
    </div>
  );
}
