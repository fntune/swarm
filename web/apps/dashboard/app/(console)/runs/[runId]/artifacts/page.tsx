import { ArtifactTable } from "@/components/artifacts/artifact-table";
import { getSpawndClient } from "@/lib/server/client";

export const dynamic = "force-dynamic";

export default async function ArtifactsPage({ params }: { params: Promise<{ runId: string }> }) {
  const { runId } = await params;
  const decoded = decodeURIComponent(runId);
  const client = await getSpawndClient();
  const artifacts = await client.runs.artifacts(decoded);

  return (
    <div className="min-h-0 flex-1 overflow-y-auto p-6">
      <ArtifactTable runId={decoded} initialArtifacts={artifacts} />
    </div>
  );
}
