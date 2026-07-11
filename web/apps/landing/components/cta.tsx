import { ForkGlyph } from "@spawnd/ui/components/logo";
import { Button } from "@spawnd/ui/components/ui/button";

import { GITHUB_URL, GitHubMark } from "@/components/github";
import { Reveal } from "@/components/reveal";

export function Cta() {
  return (
    <section className="relative overflow-hidden border-t px-6 py-20 sm:px-10 sm:py-24">
      <div
        aria-hidden="true"
        className="pointer-events-none absolute inset-0 bg-[radial-gradient(40rem_18rem_at_50%_120%,color-mix(in_oklab,var(--color-primary)_12%,transparent),transparent_70%)]"
      />
      <Reveal className="relative flex flex-col items-center gap-6 text-center">
        <ForkGlyph className="size-8 text-primary" />
        <h2 className="max-w-xl text-balance font-semibold text-2xl tracking-tight sm:text-3xl">
          Put your agents on the record.
        </h2>
        <p className="max-w-md text-balance text-[15px] text-muted-foreground leading-relaxed">
          spawnd is on GitHub — read the source, run the stack, and open an issue when something
          should work better.
        </p>
        <Button asChild size="lg">
          <a href={GITHUB_URL} target="_blank" rel="noreferrer">
            <GitHubMark className="size-4" />
            fntune/spawnd
          </a>
        </Button>
      </Reveal>
    </section>
  );
}
