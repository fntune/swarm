import { UsagePanel } from "@/components/run/usage-panel";
import { getSpawndClient } from "@/lib/server/client";

export const dynamic = "force-dynamic";

export default async function UsagePage({ params }: { params: Promise<{ runId: string }> }) {
  const { runId } = await params;
  const decoded = decodeURIComponent(runId);
  const client = await getSpawndClient();
  const usage = await client.runs.usage(decoded);

  return (
    <div className="min-h-0 flex-1 overflow-y-auto p-6">
      <UsagePanel runId={decoded} initialUsage={usage} />
    </div>
  );
}
