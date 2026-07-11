import { ChecksPanel } from "@/components/run/checks-panel";
import { getSpawndClient } from "@/lib/server/client";

export const dynamic = "force-dynamic";

export default async function ChecksPage({ params }: { params: Promise<{ runId: string }> }) {
  const { runId } = await params;
  const decoded = decodeURIComponent(runId);
  const client = await getSpawndClient();
  const checks = await client.runs.checks(decoded);

  return (
    <div className="min-h-0 flex-1 overflow-y-auto p-6">
      <ChecksPanel runId={decoded} initialChecks={checks} />
    </div>
  );
}
