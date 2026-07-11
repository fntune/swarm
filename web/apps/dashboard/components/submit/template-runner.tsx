"use client";

import type { RunTemplate } from "@spawnd/api-client";
import { EmptyState } from "@spawnd/ui/components/empty-state";
import { Button } from "@spawnd/ui/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@spawnd/ui/components/ui/select";
import { useMutation, useQuery } from "@tanstack/react-query";
import { LayersIcon, Loader2Icon, PlayIcon } from "lucide-react";
import { useRouter } from "next/navigation";
import * as React from "react";
import { toast } from "sonner";

import { browserClient, templatesQuery } from "@/lib/queries";
import { initialParameterValues, templateParameters } from "@/lib/template-parameters";
import { ParamForm } from "./param-form";

export function TemplateRunner({ initialTemplates }: { initialTemplates: RunTemplate[] }) {
  const router = useRouter();
  const templates = useQuery({ ...templatesQuery(), initialData: initialTemplates });
  const [templateId, setTemplateId] = React.useState<string>("");
  const [values, setValues] = React.useState<Record<string, string>>({});

  const rows = templates.data ?? [];
  const selected = rows.find((template) => template.id === templateId) ?? null;
  const parameters = selected ? templateParameters(selected) : [];

  const run = useMutation({
    mutationFn: () => {
      if (!selected) throw new Error("Pick a template first");
      return browserClient().templates.run(selected.id, { parameters: values });
    },
    onSuccess: (result) => {
      toast.success(`Run submitted: ${result.run_id}`);
      router.push(`/runs/${encodeURIComponent(result.run_id)}`);
    },
    onError: (error: Error) => toast.error(error.message),
  });

  if (rows.length === 0) {
    return (
      <EmptyState
        icon={LayersIcon}
        title="No templates yet"
        description="Create a template on the Templates page to submit parameterized runs."
      />
    );
  }

  return (
    <div className="flex max-w-md flex-col gap-4">
      <Select
        value={templateId}
        onValueChange={(value) => {
          setTemplateId(value);
          const template = rows.find((row) => row.id === value);
          setValues(initialParameterValues(template ? templateParameters(template) : []));
        }}
      >
        <SelectTrigger className="font-mono text-xs">
          <SelectValue placeholder="Pick a template" />
        </SelectTrigger>
        <SelectContent>
          {rows.map((template) => (
            <SelectItem key={template.id} value={template.id} className="font-mono text-xs">
              {template.name} ({template.id})
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
      {selected ? (
        <>
          {selected.description ? (
            <p className="text-muted-foreground text-xs">{selected.description}</p>
          ) : null}
          <ParamForm parameters={parameters} values={values} onChange={setValues} />
          <Button className="self-start" disabled={run.isPending} onClick={() => run.mutate()}>
            {run.isPending ? (
              <Loader2Icon className="size-4 animate-spin" />
            ) : (
              <PlayIcon className="size-4" />
            )}
            Run template
          </Button>
        </>
      ) : null}
    </div>
  );
}
