import { RunWorkspace } from "@/components/run/workspace";
import { getSpawndClient } from "@/lib/server/client";

export const dynamic = "force-dynamic";

export default async function RunPage({ params }: { params: Promise<{ runId: string }> }) {
  const { runId } = await params;
  const decoded = decodeURIComponent(runId);
  const client = await getSpawndClient();
  const detail = await client.runs.get(decoded);

  return <RunWorkspace runId={decoded} initialDetail={detail} />;
}
