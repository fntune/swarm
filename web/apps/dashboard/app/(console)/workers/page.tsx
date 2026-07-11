import { WorkerTable } from "@/components/workers/worker-table";
import { getSpawndClient } from "@/lib/server/client";

export const dynamic = "force-dynamic";

export default async function WorkersPage() {
  const client = await getSpawndClient();
  const workers = await client.workers.get();

  return (
    <div className="flex flex-col gap-6 p-6">
      <WorkerTable initialWorkers={workers} />
    </div>
  );
}
