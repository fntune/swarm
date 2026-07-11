import { Logo } from "@spawnd/ui/components/logo";

import { GITHUB_URL, GitHubMark } from "@/components/github";

export function Footer() {
  return (
    <footer className="border-t">
      <div className="mx-auto flex max-w-6xl flex-col gap-4 border-x px-6 py-10 sm:flex-row sm:items-center sm:justify-between sm:px-10">
        <div className="flex flex-col gap-2">
          <Logo />
          <p className="font-mono text-muted-foreground text-xs">
            deployed-first agent orchestration
          </p>
        </div>
        <div className="flex items-center gap-6 font-mono text-muted-foreground text-xs">
          <a
            href={GITHUB_URL}
            target="_blank"
            rel="noreferrer"
            className="inline-flex items-center gap-1.5 transition-colors hover:text-foreground"
          >
            <GitHubMark className="size-3.5" />
            fntune/spawnd
          </a>
          <span>© 2026 spawnd</span>
        </div>
      </div>
    </footer>
  );
}
