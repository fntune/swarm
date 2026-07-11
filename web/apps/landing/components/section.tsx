import { Reveal } from "@/components/reveal";

export function Section({
  id,
  number,
  label,
  title,
  intro,
  children,
}: {
  id: string;
  number: string;
  label: string;
  title: string;
  intro?: string;
  children: React.ReactNode;
}) {
  return (
    <section id={id} className="scroll-mt-14 border-t px-6 py-16 sm:px-10 sm:py-20">
      <Reveal>
        <p className="flex items-baseline gap-3 font-mono text-xs">
          <span className="text-primary">{number}</span>
          <span className="text-muted-foreground uppercase tracking-[0.2em]">{label}</span>
        </p>
        <h2 className="mt-4 max-w-2xl text-balance font-semibold text-2xl tracking-tight sm:text-3xl">
          {title}
        </h2>
        {intro ? (
          <p className="mt-3 max-w-2xl text-[15px] text-muted-foreground leading-relaxed">
            {intro}
          </p>
        ) : null}
      </Reveal>
      <div className="mt-10">{children}</div>
    </section>
  );
}
