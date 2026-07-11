import type { RunTemplate } from "@spawnd/api-client";

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

export function initialParameterValues(parameters: string[]): Record<string, string> {
  return Object.fromEntries(parameters.map((name) => [name, ""]));
}
