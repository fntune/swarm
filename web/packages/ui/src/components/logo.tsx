import { cn } from "../lib/utils";

export function ForkGlyph({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" aria-hidden="true" className={className}>
      <path
        d="M7 12h3c3 0 3-6 6-6h0.5"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
      />
      <path
        d="M10 12c3 0 3 6 6 6h0.5"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
      />
      <circle cx="5" cy="12" r="2.5" fill="currentColor" />
      <circle cx="19" cy="6" r="2" stroke="currentColor" strokeWidth="2" />
      <circle cx="19" cy="18" r="2" stroke="currentColor" strokeWidth="2" />
    </svg>
  );
}

export function Logo({
  className,
  glyphClassName,
  wordmarkClassName,
}: {
  className?: string;
  glyphClassName?: string;
  wordmarkClassName?: string;
}) {
  return (
    <span className={cn("inline-flex items-center gap-2", className)}>
      <ForkGlyph className={cn("size-5 text-primary", glyphClassName)} />
      <span
        className={cn(
          "font-mono font-semibold text-base lowercase tracking-tight",
          wordmarkClassName,
        )}
      >
        spawnd
      </span>
    </span>
  );
}
