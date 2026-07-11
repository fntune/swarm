"use client";

import type { RunTemplate, Schedule } from "@spawnd/api-client";
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
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@spawnd/ui/components/ui/select";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@spawnd/ui/components/ui/table";
import { cn } from "@spawnd/ui/lib/utils";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CalendarClockIcon, Loader2Icon, PauseIcon, PlayIcon, PlusIcon } from "lucide-react";
import Link from "next/link";
import * as React from "react";
import { toast } from "sonner";

import { ParamForm, templateParameters } from "@/components/submit/param-form";
import { formatDurationMs } from "@/lib/format";
import { browserClient, schedulesQuery, templatesQuery } from "@/lib/queries";

function CreateScheduleDialog({ templates }: { templates: RunTemplate[] }) {
  const queryClient = useQueryClient();
  const [open, setOpen] = React.useState(false);
  const [id, setId] = React.useState("");
  const [name, setName] = React.useState("");
  const [templateId, setTemplateId] = React.useState("");
  const [intervalSeconds, setIntervalSeconds] = React.useState("3600");
  const [values, setValues] = React.useState<Record<string, string>>({});

  const selected = templates.find((template) => template.id === templateId) ?? null;
  const parameters = selected ? templateParameters(selected) : [];

  const create = useMutation({
    mutationFn: () =>
      browserClient().schedules.create({
        id: id.trim(),
        template_id: templateId,
        name: name.trim() || id.trim(),
        interval_seconds: Number.parseInt(intervalSeconds, 10),
        parameters: values,
        status: "paused",
      }),
    onSuccess: () => {
      toast.success("Schedule saved (paused — activate when ready)");
      queryClient.invalidateQueries({ queryKey: ["schedules"] });
      setOpen(false);
    },
    onError: (error: Error) => toast.error(error.message),
  });

  const intervalValid = Number.parseInt(intervalSeconds, 10) > 0;

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button size="sm">
          <PlusIcon className="size-4" />
          New schedule
        </Button>
      </DialogTrigger>
      <DialogContent className="flex max-h-[85vh] flex-col gap-4 overflow-y-auto sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Create schedule</DialogTitle>
        </DialogHeader>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="sched-id" className="font-mono text-xs">
            id
          </Label>
          <Input
            id="sched-id"
            value={id}
            onChange={(event) => setId(event.target.value)}
            placeholder="nightly"
            className="font-mono text-xs"
          />
        </div>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="sched-name" className="font-mono text-xs">
            name
          </Label>
          <Input
            id="sched-name"
            value={name}
            onChange={(event) => setName(event.target.value)}
            className="font-mono text-xs"
          />
        </div>
        <div className="flex flex-col gap-1.5">
          <Label className="font-mono text-xs">template</Label>
          <Select
            value={templateId}
            onValueChange={(value) => {
              setTemplateId(value);
              setValues({});
            }}
          >
            <SelectTrigger className="font-mono text-xs">
              <SelectValue placeholder="Pick a template" />
            </SelectTrigger>
            <SelectContent>
              {templates.map((template) => (
                <SelectItem key={template.id} value={template.id} className="font-mono text-xs">
                  {template.name} ({template.id})
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="sched-interval" className="font-mono text-xs">
            interval_seconds
          </Label>
          <Input
            id="sched-interval"
            value={intervalSeconds}
            onChange={(event) => setIntervalSeconds(event.target.value)}
            inputMode="numeric"
            className="font-mono text-xs"
          />
        </div>
        {selected ? (
          <ParamForm parameters={parameters} values={values} onChange={setValues} />
        ) : null}
        <Button
          className="self-start"
          disabled={create.isPending || !id.trim() || !templateId || !intervalValid}
          onClick={() => create.mutate()}
        >
          {create.isPending ? <Loader2Icon className="size-4 animate-spin" /> : null}
          Save schedule
        </Button>
      </DialogContent>
    </Dialog>
  );
}

function ScheduleStatusButton({ schedule }: { schedule: Schedule }) {
  const queryClient = useQueryClient();
  const next = schedule.status === "active" ? "paused" : "active";
  const toggle = useMutation({
    mutationFn: () => browserClient().schedules.setStatus(schedule.id, next),
    onMutate: async () => {
      await queryClient.cancelQueries({ queryKey: ["schedules"] });
      const previous = queryClient.getQueryData<Schedule[]>(["schedules"]);
      queryClient.setQueryData<Schedule[]>(["schedules"], (current) =>
        (current ?? []).map((row) => (row.id === schedule.id ? { ...row, status: next } : row)),
      );
      return { previous };
    },
    onError: (error: Error, _variables, context) => {
      if (context?.previous) queryClient.setQueryData(["schedules"], context.previous);
      toast.error(error.message);
    },
    onSettled: () => queryClient.invalidateQueries({ queryKey: ["schedules"] }),
  });

  return (
    <Button variant="outline" size="sm" disabled={toggle.isPending} onClick={() => toggle.mutate()}>
      {schedule.status === "active" ? (
        <>
          <PauseIcon className="size-3.5" />
          Pause
        </>
      ) : (
        <>
          <PlayIcon className="size-3.5" />
          Activate
        </>
      )}
    </Button>
  );
}

export function ScheduleManager({
  initialSchedules,
  initialTemplates,
}: {
  initialSchedules: Schedule[];
  initialTemplates: RunTemplate[];
}) {
  const schedules = useQuery({
    ...schedulesQuery(),
    initialData: initialSchedules,
    refetchInterval: 30_000,
  });
  const templates = useQuery({ ...templatesQuery(), initialData: initialTemplates });
  const rows = schedules.data ?? [];

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between">
        <h2 className="font-mono text-muted-foreground text-xs uppercase tracking-wider">
          schedules
        </h2>
        <CreateScheduleDialog templates={templates.data ?? []} />
      </div>
      {rows.length === 0 ? (
        <EmptyState
          icon={CalendarClockIcon}
          title="No schedules"
          description="Schedules submit a template on an interval. New schedules start paused."
        />
      ) : (
        <div className="overflow-x-auto rounded-lg border">
          <Table className="text-[13px]">
            <TableHeader>
              <TableRow className="hover:bg-transparent">
                <TableHead>schedule</TableHead>
                <TableHead>template</TableHead>
                <TableHead>status</TableHead>
                <TableHead>interval</TableHead>
                <TableHead>next run</TableHead>
                <TableHead>last run</TableHead>
                <TableHead className="w-24" />
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.map((schedule) => (
                <TableRow key={schedule.id}>
                  <TableCell>
                    <span className="block font-mono">{schedule.id}</span>
                    {schedule.name !== schedule.id ? (
                      <span className="block text-muted-foreground text-xs">{schedule.name}</span>
                    ) : null}
                  </TableCell>
                  <TableCell className="font-mono text-muted-foreground text-xs">
                    {schedule.template_id}
                  </TableCell>
                  <TableCell>
                    <span
                      className={cn(
                        "inline-flex items-center gap-1.5 rounded-md border bg-card px-2 py-0.5 font-mono text-xs",
                      )}
                    >
                      <span
                        aria-hidden="true"
                        className={cn(
                          "size-2 rounded-full",
                          schedule.status === "active" ? "bg-status-completed" : "bg-status-paused",
                        )}
                      />
                      {schedule.status}
                    </span>
                  </TableCell>
                  <TableCell className="font-mono text-muted-foreground text-xs tabular-nums">
                    {formatDurationMs(schedule.interval_seconds * 1000)}
                  </TableCell>
                  <TableCell className="whitespace-nowrap text-muted-foreground">
                    <RelativeTime value={schedule.next_run_at} />
                  </TableCell>
                  <TableCell className="whitespace-nowrap text-muted-foreground">
                    {schedule.last_run_id ? (
                      <Link
                        href={`/runs/${encodeURIComponent(schedule.last_run_id)}`}
                        className="font-mono text-xs hover:text-primary"
                      >
                        {schedule.last_run_id}
                      </Link>
                    ) : (
                      "—"
                    )}
                  </TableCell>
                  <TableCell>
                    <ScheduleStatusButton schedule={schedule} />
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
