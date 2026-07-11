import { TracesPanel } from "@/components/run/traces-panel";
import { getSpawndClient } from "@/lib/server/client";

export const dynamic = "force-dynamic";

export default async function TracesPage({ params }: { params: Promise<{ runId: string }> }) {
  const { runId } = await params;
  const decoded = decodeURIComponent(runId);
  const client = await getSpawndClient();
  const traces = await client.runs.traces(decoded);

  return (
    <div className="min-h-0 flex-1 overflow-y-auto p-6">
      <TracesPanel runId={decoded} initialTraces={traces} />
    </div>
  );
}
