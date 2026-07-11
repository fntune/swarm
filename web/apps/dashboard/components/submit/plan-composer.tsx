"use client";

import { yaml as yamlLanguage } from "@codemirror/lang-yaml";
import { SpawndApiError } from "@spawnd/api-client";
import { Button } from "@spawnd/ui/components/ui/button";
import { Input } from "@spawnd/ui/components/ui/input";
import { Label } from "@spawnd/ui/components/ui/label";
import { useMutation } from "@tanstack/react-query";
import CodeMirror from "@uiw/react-codemirror";
import { Loader2Icon, PlayIcon, TriangleAlertIcon } from "lucide-react";
import { useRouter } from "next/navigation";
import { useTheme } from "next-themes";
import * as React from "react";
import { toast } from "sonner";
import { parse as parseYaml } from "yaml";

import { browserClient } from "@/lib/queries";

const DEFAULT_PLAN = `name: my-run
agents:
  - name: worker
    prompt: Describe the change you want made.
    check: pytest tests/
`;

export function PlanComposer() {
  const router = useRouter();
  const { resolvedTheme } = useTheme();
  const [mounted, setMounted] = React.useState(false);
  const [source, setSource] = React.useState(DEFAULT_PLAN);
  const [runId, setRunId] = React.useState("");
  const [sourceRepo, setSourceRepo] = React.useState("");
  const [sourceRef, setSourceRef] = React.useState("");
  const [problems, setProblems] = React.useState<string[]>([]);

  React.useEffect(() => {
    setMounted(true);
  }, []);

  const submit = useMutation({
    mutationFn: async () => {
      let plan: unknown;
      try {
        plan = parseYaml(source);
      } catch (error) {
        throw new Error(`YAML parse error: ${(error as Error).message}`);
      }
      if (!plan || typeof plan !== "object" || Array.isArray(plan)) {
        throw new Error("Plan must be a YAML mapping with name and agents");
      }
      return browserClient().runs.submit({
        plan: plan as { name: string; agents: Record<string, unknown>[] },
        run_id: runId.trim() || undefined,
        source_repo: sourceRepo.trim() || undefined,
        source_ref: sourceRef.trim() || undefined,
      });
    },
    onSuccess: (result) => {
      toast.success(`Run submitted: ${result.run_id}`);
      router.push(`/runs/${encodeURIComponent(result.run_id)}`);
    },
    onError: (error: Error) => {
      if (error instanceof SpawndApiError) {
        setProblems(
          error.validationMessages.length > 0 ? error.validationMessages : [error.message],
        );
      } else {
        setProblems([error.message]);
      }
    },
  });

  return (
    <div className="flex max-w-4xl flex-col gap-4">
      <div className="overflow-hidden rounded-lg border">
        {mounted ? (
          <CodeMirror
            value={source}
            onChange={(value) => setSource(value)}
            extensions={[yamlLanguage()]}
            theme={resolvedTheme === "dark" ? "dark" : "light"}
            minHeight="320px"
            style={{ fontSize: 13 }}
            basicSetup={{ lineNumbers: true, foldGutter: true, highlightActiveLine: true }}
          />
        ) : (
          <div className="h-80 bg-muted/30" />
        )}
      </div>
      <div className="grid gap-3 sm:grid-cols-3">
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="source-repo" className="font-mono text-xs">
            source_repo
          </Label>
          <Input
            id="source-repo"
            value={sourceRepo}
            onChange={(event) => setSourceRepo(event.target.value)}
            placeholder="/path/to/repo or git URL"
            className="font-mono text-xs"
          />
        </div>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="source-ref" className="font-mono text-xs">
            source_ref
          </Label>
          <Input
            id="source-ref"
            value={sourceRef}
            onChange={(event) => setSourceRef(event.target.value)}
            placeholder="origin/main"
            className="font-mono text-xs"
          />
        </div>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="run-id" className="font-mono text-xs">
            run_id (optional)
          </Label>
          <Input
            id="run-id"
            value={runId}
            onChange={(event) => setRunId(event.target.value)}
            placeholder="auto-generated"
            className="font-mono text-xs"
          />
        </div>
      </div>
      {problems.length > 0 ? (
        <div className="flex flex-col gap-1.5 rounded-md border border-status-failed/40 bg-status-failed/5 px-3 py-2.5">
          <span className="flex items-center gap-1.5 font-medium text-status-failed text-xs">
            <TriangleAlertIcon className="size-3.5" />
            Plan rejected
          </span>
          <ul className="flex flex-col gap-0.5">
            {problems.map((problem) => (
              <li key={problem} className="font-mono text-muted-foreground text-xs">
                {problem}
              </li>
            ))}
          </ul>
        </div>
      ) : null}
      <Button
        className="self-start"
        disabled={submit.isPending}
        onClick={() => {
          setProblems([]);
          submit.mutate();
        }}
      >
        {submit.isPending ? (
          <Loader2Icon className="size-4 animate-spin" />
        ) : (
          <PlayIcon className="size-4" />
        )}
        Submit run
      </Button>
    </div>
  );
}
