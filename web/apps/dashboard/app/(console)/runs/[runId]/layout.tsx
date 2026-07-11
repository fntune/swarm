import { SpawndApiError } from "@spawnd/api-client";
import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { RunHeader } from "@/components/run/header";
import { RunTabs } from "@/components/run/tabs";
import { getSpawndClient } from "@/lib/server/client";

export const dynamic = "force-dynamic";

export async function generateMetadata({
  params,
}: {
  params: Promise<{ runId: string }>;
}): Promise<Metadata> {
  const { runId } = await params;
  return { title: `${decodeURIComponent(runId)} — spawnd console` };
}

export default async function RunLayout({
  children,
  params,
}: {
  children: React.ReactNode;
  params: Promise<{ runId: string }>;
}) {
  const { runId } = await params;
  const decoded = decodeURIComponent(runId);
  const client = await getSpawndClient();

  let detail: Awaited<ReturnType<typeof client.runs.get>>;
  try {
    detail = await client.runs.get(decoded);
  } catch (error) {
    if (error instanceof SpawndApiError && error.status === 404) {
      notFound();
    }
    throw error;
  }

  return (
    <div className="flex h-[calc(100vh-3.5rem)] flex-col">
      <RunHeader runId={decoded} initialDetail={detail} />
      <RunTabs runId={decoded} />
      {children}
    </div>
  );
}
