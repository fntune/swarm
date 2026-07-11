import { Logo } from "@spawnd/ui/components/logo";
import { ThemeToggle } from "@spawnd/ui/components/theme-toggle";
import { Button } from "@spawnd/ui/components/ui/button";

import { GITHUB_URL, GitHubMark } from "@/components/github";

const NAV = [
  { href: "#capabilities", label: "capabilities" },
  { href: "#architecture", label: "architecture" },
  { href: "#plans", label: "plans" },
  { href: "#quickstart", label: "quickstart" },
];

export function Header() {
  return (
    <header className="sticky top-0 z-40 border-b bg-background/80 backdrop-blur">
      <div className="mx-auto flex h-14 max-w-6xl items-center justify-between border-x px-6 sm:px-10">
        <a href="#top" aria-label="spawnd — back to top">
          <Logo />
        </a>
        <nav className="hidden items-center gap-6 font-mono text-muted-foreground text-xs md:flex">
          {NAV.map((item) => (
            <a key={item.href} href={item.href} className="transition-colors hover:text-foreground">
              {item.label}
            </a>
          ))}
        </nav>
        <div className="flex items-center gap-1.5">
          <Button asChild variant="ghost" size="icon" className="size-8">
            <a href={GITHUB_URL} target="_blank" rel="noreferrer" aria-label="spawnd on GitHub">
              <GitHubMark className="size-4" />
            </a>
          </Button>
          <ThemeToggle />
        </div>
      </div>
    </header>
  );
}
