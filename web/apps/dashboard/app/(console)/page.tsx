import { FleetStrip } from "@/components/overview/fleet-strip";
import { RunTable } from "@/components/overview/run-table";
import { getSpawndClient } from "@/lib/server/client";

export const dynamic = "force-dynamic";

export default async function OverviewPage() {
  const client = await getSpawndClient();
  const [workers, runs] = await Promise.all([
    client.workers.get(),
    client.runs.list({ limit: 100 }),
  ]);

  return (
    <div className="flex flex-col gap-6 p-6">
      <FleetStrip initialWorkers={workers} initialRuns={runs} />
      <RunTable initialRuns={runs} />
    </div>
  );
}
