"use client";

import type { RunTemplate } from "@spawnd/api-client";
import { Input } from "@spawnd/ui/components/ui/input";
import { Label } from "@spawnd/ui/components/ui/label";

/** Extract `{name}` format_map tokens from a template's text fields. */
export function templateParameters(template: RunTemplate): string[] {
  const sources = [
    template.plan_template,
    template.source_repo_template ?? "",
    template.source_ref_template ?? "",
  ].join("\n");
  const names = new Set<string>();
  for (const match of sources.matchAll(/\{([a-zA-Z0-9_]+)\}/g)) {
    if (match[1]) names.add(match[1]);
  }
  return [...names].sort();
}

export function ParamForm({
  parameters,
  values,
  onChange,
}: {
  parameters: string[];
  values: Record<string, string>;
  onChange: (next: Record<string, string>) => void;
}) {
  if (parameters.length === 0) {
    return <p className="text-muted-foreground text-xs">This template takes no parameters.</p>;
  }
  return (
    <div className="flex flex-col gap-3">
      {parameters.map((name) => (
        <div key={name} className="flex flex-col gap-1.5">
          <Label htmlFor={`param-${name}`} className="font-mono text-xs">
            {name}
          </Label>
          <Input
            id={`param-${name}`}
            value={values[name] ?? ""}
            onChange={(event) => onChange({ ...values, [name]: event.target.value })}
            className="font-mono text-xs"
          />
        </div>
      ))}
    </div>
  );
}
