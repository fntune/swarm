import { cn } from "../lib/utils";

/**
 * Terminal chrome shared by the landing hero and dashboard log panes.
 * The body is always dark — terminals stay terminals in both themes.
 */
export function TerminalFrame({
  title,
  children,
  className,
  bodyClassName,
}: {
  title?: string;
  children: React.ReactNode;
  className?: string;
  bodyClassName?: string;
}) {
  return (
    <div
      className={cn(
        "overflow-hidden rounded-lg border border-zinc-700/60 bg-zinc-950 shadow-lg",
        className,
      )}
    >
      <div className="flex items-center gap-2 border-zinc-800 border-b bg-zinc-900 px-3 py-2">
        <span aria-hidden="true" className="flex gap-1.5">
          <span className="size-2.5 rounded-full bg-zinc-700" />
          <span className="size-2.5 rounded-full bg-zinc-700" />
          <span className="size-2.5 rounded-full bg-zinc-700" />
        </span>
        {title ? <span className="ml-1 font-mono text-xs text-zinc-400">{title}</span> : null}
      </div>
      <div
        className={cn(
          "overflow-auto p-4 font-mono text-[13px] text-zinc-100 leading-relaxed",
          bodyClassName,
        )}
      >
        {children}
      </div>
    </div>
  );
}
