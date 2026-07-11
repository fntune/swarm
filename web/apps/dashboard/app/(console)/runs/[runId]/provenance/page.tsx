import { ProvenancePanel } from "@/components/run/provenance-panel";
import { getSpawndClient } from "@/lib/server/client";

export const dynamic = "force-dynamic";

export default async function ProvenancePage({ params }: { params: Promise<{ runId: string }> }) {
  const { runId } = await params;
  const decoded = decodeURIComponent(runId);
  const client = await getSpawndClient();
  const provenance = await client.runs.provenance(decoded);

  return (
    <div className="min-h-0 flex-1 overflow-y-auto p-6">
      <ProvenancePanel runId={decoded} initialProvenance={provenance} />
    </div>
  );
}
