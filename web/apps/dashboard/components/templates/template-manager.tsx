"use client";

import type { RunTemplate } from "@spawnd/api-client";
import { EmptyState } from "@spawnd/ui/components/empty-state";
import { RelativeTime } from "@spawnd/ui/components/relative-time";
import { Button } from "@spawnd/ui/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@spawnd/ui/components/ui/dialog";
import { Input } from "@spawnd/ui/components/ui/input";
import { Label } from "@spawnd/ui/components/ui/label";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@spawnd/ui/components/ui/table";
import { Textarea } from "@spawnd/ui/components/ui/textarea";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { LayersIcon, Loader2Icon, PlayIcon, PlusIcon } from "lucide-react";
import { useRouter } from "next/navigation";
import * as React from "react";
import { toast } from "sonner";

import { ParamForm, templateParameters } from "@/components/submit/param-form";
import { browserClient, templatesQuery } from "@/lib/queries";

const DEFAULT_TEMPLATE = `name: {name}
agents:
  - name: worker
    prompt: |
      {prompt}
    check: pytest tests/
`;

function CreateTemplateDialog() {
  const queryClient = useQueryClient();
  const [open, setOpen] = React.useState(false);
  const [id, setId] = React.useState("");
  const [name, setName] = React.useState("");
  const [description, setDescription] = React.useState("");
  const [planTemplate, setPlanTemplate] = React.useState(DEFAULT_TEMPLATE);
  const [sourceRepoTemplate, setSourceRepoTemplate] = React.useState("");
  const [sourceRefTemplate, setSourceRefTemplate] = React.useState("");

  const create = useMutation({
    mutationFn: () =>
      browserClient().templates.create({
        id: id.trim(),
        name: name.trim() || id.trim(),
        plan_template: planTemplate,
        description: description.trim() || undefined,
        source_repo_template: sourceRepoTemplate.trim() || undefined,
        source_ref_template: sourceRefTemplate.trim() || undefined,
      }),
    onSuccess: () => {
      toast.success("Template saved");
      queryClient.invalidateQueries({ queryKey: ["templates"] });
      setOpen(false);
    },
    onError: (error: Error) => toast.error(error.message),
  });

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button size="sm">
          <PlusIcon className="size-4" />
          New template
        </Button>
      </DialogTrigger>
      <DialogContent className="flex max-h-[85vh] flex-col gap-4 overflow-y-auto sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>Create template</DialogTitle>
        </DialogHeader>
        <div className="grid gap-3 sm:grid-cols-2">
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="tpl-id" className="font-mono text-xs">
              id
            </Label>
            <Input
              id="tpl-id"
              value={id}
              onChange={(event) => setId(event.target.value)}
              placeholder="nightly-refactor"
              className="font-mono text-xs"
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="tpl-name" className="font-mono text-xs">
              name
            </Label>
            <Input
              id="tpl-name"
              value={name}
              onChange={(event) => setName(event.target.value)}
              className="font-mono text-xs"
            />
          </div>
        </div>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="tpl-description" className="font-mono text-xs">
            description
          </Label>
          <Input
            id="tpl-description"
            value={description}
            onChange={(event) => setDescription(event.target.value)}
            className="text-xs"
          />
        </div>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="tpl-plan" className="font-mono text-xs">
            plan_template — use {"{param}"} placeholders
          </Label>
          <Textarea
            id="tpl-plan"
            value={planTemplate}
            onChange={(event) => setPlanTemplate(event.target.value)}
            rows={10}
            className="font-mono text-xs"
          />
        </div>
        <div className="grid gap-3 sm:grid-cols-2">
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="tpl-repo" className="font-mono text-xs">
              source_repo_template
            </Label>
            <Input
              id="tpl-repo"
              value={sourceRepoTemplate}
              onChange={(event) => setSourceRepoTemplate(event.target.value)}
              placeholder="https://github.com/{repo}.git"
              className="font-mono text-xs"
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="tpl-ref" className="font-mono text-xs">
              source_ref_template
            </Label>
            <Input
              id="tpl-ref"
              value={sourceRefTemplate}
              onChange={(event) => setSourceRefTemplate(event.target.value)}
              placeholder="origin/{head_ref}"
              className="font-mono text-xs"
            />
          </div>
        </div>
        <Button
          className="self-start"
          disabled={create.isPending || !id.trim() || !planTemplate.trim()}
          onClick={() => create.mutate()}
        >
          {create.isPending ? <Loader2Icon className="size-4 animate-spin" /> : null}
          Save template
        </Button>
      </DialogContent>
    </Dialog>
  );
}

function RunTemplateDialog({ template }: { template: RunTemplate }) {
  const router = useRouter();
  const [open, setOpen] = React.useState(false);
  const [values, setValues] = React.useState<Record<string, string>>({});
  const parameters = templateParameters(template);

  const run = useMutation({
    mutationFn: () => browserClient().templates.run(template.id, { parameters: values }),
    onSuccess: (result) => {
      toast.success(`Run submitted: ${result.run_id}`);
      setOpen(false);
      router.push(`/runs/${encodeURIComponent(result.run_id)}`);
    },
    onError: (error: Error) => toast.error(error.message),
  });

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button variant="outline" size="sm">
          <PlayIcon className="size-3.5" />
          Run
        </Button>
      </DialogTrigger>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle className="font-mono text-sm">run {template.id}</DialogTitle>
        </DialogHeader>
        <ParamForm parameters={parameters} values={values} onChange={setValues} />
        <Button className="self-start" disabled={run.isPending} onClick={() => run.mutate()}>
          {run.isPending ? (
            <Loader2Icon className="size-4 animate-spin" />
          ) : (
            <PlayIcon className="size-4" />
          )}
          Submit
        </Button>
      </DialogContent>
    </Dialog>
  );
}

export function TemplateManager({ initialTemplates }: { initialTemplates: RunTemplate[] }) {
  const templates = useQuery({ ...templatesQuery(), initialData: initialTemplates });
  const rows = templates.data ?? [];

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between">
        <h2 className="font-mono text-muted-foreground text-xs uppercase tracking-wider">
          run templates
        </h2>
        <CreateTemplateDialog />
      </div>
      {rows.length === 0 ? (
        <EmptyState
          icon={LayersIcon}
          title="No templates"
          description="Templates are parameterized plans used by schedules, webhooks, and one-off runs."
        />
      ) : (
        <div className="overflow-x-auto rounded-lg border">
          <Table className="text-[13px]">
            <TableHeader>
              <TableRow className="hover:bg-transparent">
                <TableHead>id</TableHead>
                <TableHead>name</TableHead>
                <TableHead>parameters</TableHead>
                <TableHead>updated</TableHead>
                <TableHead className="w-20" />
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.map((template) => (
                <TableRow key={template.id}>
                  <TableCell className="font-mono">{template.id}</TableCell>
                  <TableCell>
                    <span className="block">{template.name}</span>
                    {template.description ? (
                      <span className="block text-muted-foreground text-xs">
                        {template.description}
                      </span>
                    ) : null}
                  </TableCell>
                  <TableCell className="font-mono text-muted-foreground text-xs">
                    {templateParameters(template).join(", ") || "—"}
                  </TableCell>
                  <TableCell className="whitespace-nowrap text-muted-foreground">
                    <RelativeTime value={template.updated_at} />
                  </TableCell>
                  <TableCell>
                    <RunTemplateDialog template={template} />
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}
    </div>
  );
}
